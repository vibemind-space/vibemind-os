/**
 * Port Allocator for VNC and App ports
 *
 * VNC Ports: 6081, 6082, 6083, ...
 * App Ports: 3001, 3002, 3003, ...
 */

import { exec } from 'child_process'
import { promisify } from 'util'
import * as net from 'net'

const execAsync = promisify(exec)

interface PortAllocation {
  vncPort: number
  appPort: number
}

export class PortAllocator {
  private vncBasePort = 6081
  private appBasePort = 3001
  private maxPorts = 20

  private allocations = new Map<string, PortAllocation>()
  private usedVncPorts = new Set<number>()
  private usedAppPorts = new Set<number>()

  /**
   * Allocate a VNC port for a project
   */
  async allocate(projectId: string): Promise<number> {
    // Return existing allocation if exists
    const existing = this.allocations.get(projectId)
    if (existing) {
      return existing.vncPort
    }

    // Find next available VNC port (checks OS-level availability)
    const vncPort = await this.findNextPort(this.vncBasePort, this.usedVncPorts)
    this.usedVncPorts.add(vncPort)

    // Initialize allocation (app port allocated separately)
    this.allocations.set(projectId, { vncPort, appPort: 0 })

    return vncPort
  }

  /**
   * Allocate an app port for a project
   */
  async allocateAppPort(projectId: string): Promise<number> {
    const existing = this.allocations.get(projectId)
    if (existing && existing.appPort > 0) {
      return existing.appPort
    }

    // Find next available app port (checks OS-level availability)
    const appPort = await this.findNextPort(this.appBasePort, this.usedAppPorts)
    this.usedAppPorts.add(appPort)

    if (existing) {
      existing.appPort = appPort
    } else {
      this.allocations.set(projectId, { vncPort: 0, appPort })
    }

    return appPort
  }

  /**
   * Release ports for a project
   */
  release(projectId: string): void {
    const allocation = this.allocations.get(projectId)
    if (allocation) {
      this.usedVncPorts.delete(allocation.vncPort)
      this.usedAppPorts.delete(allocation.appPort)
      this.allocations.delete(projectId)
    }
  }

  /**
   * Get VNC port for a project
   */
  getVncPort(projectId: string): number | undefined {
    return this.allocations.get(projectId)?.vncPort
  }

  /**
   * Get app port for a project
   */
  getAppPort(projectId: string): number | undefined {
    return this.allocations.get(projectId)?.appPort
  }

  /**
   * Get all port allocations
   */
  getAllAllocations(): Map<string, PortAllocation> {
    return new Map(this.allocations)
  }

  /**
   * Check if a port is actually free on the OS by attempting to bind to it.
   */
  private isPortFreeOnOS(port: number): Promise<boolean> {
    return new Promise((resolve) => {
      const server = net.createServer()
      server.once('error', () => resolve(false))
      server.once('listening', () => {
        server.close(() => resolve(true))
      })
      server.listen(port, '0.0.0.0')
    })
  }

  /**
   * Find next available port (checks both internal tracking and OS-level availability)
   */
  private async findNextPort(basePort: number, usedPorts: Set<number>): Promise<number> {
    for (let i = 0; i < this.maxPorts; i++) {
      const port = basePort + i
      if (usedPorts.has(port)) continue
      if (await this.isPortFreeOnOS(port)) {
        return port
      }
      console.log(`[PortAllocator] Port ${port} is in use on OS, skipping`)
    }
    throw new Error(`No available ports in range ${basePort}-${basePort + this.maxPorts}`)
  }

  /**
   * Check if a specific port is available
   */
  isPortAvailable(port: number): boolean {
    return !this.usedVncPorts.has(port) && !this.usedAppPorts.has(port)
  }

  /**
   * Sync port allocations with running Docker containers
   * Call this on app startup to detect containers from previous sessions
   */
  async syncWithDocker(): Promise<void> {
    try {
      // Find all running generation-/project- containers and their ports
      const { stdout } = await execAsync(
        'docker ps --format "{{.Names}}|{{.Ports}}"'
      )

      for (const line of stdout.split('\n').filter(Boolean)) {
        const [name, ports] = line.split('|')

        // Only process our containers
        if (!name.startsWith('generation-') && !name.startsWith('project-')) {
          continue
        }

        // Parse port bindings like "0.0.0.0:6081->6080/tcp, 0.0.0.0:3001->5173/tcp"
        const vncMatch = ports?.match(/0\.0\.0\.0:(\d+)->6080/)
        const appMatch = ports?.match(/0\.0\.0\.0:(\d+)->5173/)

        if (vncMatch) {
          const vncPort = parseInt(vncMatch[1])
          this.usedVncPorts.add(vncPort)
        }
        if (appMatch) {
          const appPort = parseInt(appMatch[1])
          this.usedAppPorts.add(appPort)
        }

        // Extract projectId from container name
        const projectId = name.replace(/^(generation-|project-)/, '')
        if (vncMatch || appMatch) {
          this.allocations.set(projectId, {
            vncPort: vncMatch ? parseInt(vncMatch[1]) : 0,
            appPort: appMatch ? parseInt(appMatch[1]) : 0
          })
        }
      }

      console.log(`[PortAllocator] Synced with Docker: ${this.usedVncPorts.size} VNC ports, ${this.usedAppPorts.size} app ports in use`)
    } catch (error) {
      // No containers found or docker not running
      console.log('[PortAllocator] No existing containers found')
    }
  }

  /**
   * Cleanup all stale generation/project containers
   * Call this on app startup to ensure clean state
   */
  async cleanupStaleContainers(): Promise<void> {
    try {
      const { stdout } = await execAsync(
        'docker ps -a --format "{{.Names}}"'
      )

      const containers = stdout.split('\n')
        .filter(name => name.startsWith('generation-') || name.startsWith('project-'))

      for (const name of containers) {
        console.log(`[PortAllocator] Removing stale container: ${name}`)
        try {
          await execAsync(`docker rm -f ${name}`)
        } catch {
          // Container already gone
        }
      }

      // Clear all allocations since containers are gone
      this.allocations.clear()
      this.usedVncPorts.clear()
      this.usedAppPorts.clear()

      console.log(`[PortAllocator] Cleaned up ${containers.length} stale containers`)
    } catch {
      // No containers or docker not running
      console.log('[PortAllocator] No stale containers to clean')
    }
  }
}
