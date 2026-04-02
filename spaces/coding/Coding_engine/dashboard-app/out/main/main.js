"use strict";
const electron = require("electron");
const path = require("path");
const fs = require("fs");
const child_process = require("child_process");
const dotenv = require("dotenv");
const util = require("util");
const net = require("net");
function _interopNamespaceDefault(e) {
  const n = Object.create(null, { [Symbol.toStringTag]: { value: "Module" } });
  if (e) {
    for (const k in e) {
      if (k !== "default") {
        const d = Object.getOwnPropertyDescriptor(e, k);
        Object.defineProperty(n, k, d.get ? d : {
          enumerable: true,
          get: () => e[k]
        });
      }
    }
  }
  n.default = e;
  return Object.freeze(n);
}
const dotenv__namespace = /* @__PURE__ */ _interopNamespaceDefault(dotenv);
const net__namespace = /* @__PURE__ */ _interopNamespaceDefault(net);
const execAsync$1 = util.promisify(child_process.exec);
function sanitizeContainerName(name) {
  return name.normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/[^a-zA-Z0-9_.-]/g, "-").replace(/^[^a-zA-Z0-9]+/, "").replace(/-+/g, "-").substring(0, 128);
}
class DockerManager {
  containers = /* @__PURE__ */ new Map();
  engineProcess = null;
  engineRunning = false;
  // Path to Coding Engine root (parent of dashboard-app)
  // __dirname in built code = .../dashboard-app/out/main/
  // We need to go up 3 levels: out/main/ → out/ → dashboard-app/ → Coding_engine/
  engineRoot = path.join(__dirname, "..", "..", "..");
  /**
   * Check if a file or directory exists
   */
  async fileExists(path2) {
    return fs.existsSync(path2);
  }
  /**
   * Start the Coding Engine Docker stack
   */
  async startEngine() {
    try {
      const composeFile = path.join(this.engineRoot, "infra", "docker", "docker-compose.dashboard.yml");
      const { stdout, stderr } = await execAsync$1(
        `docker-compose -f "${composeFile}" up -d`,
        { cwd: this.engineRoot }
      );
      this.engineRunning = true;
      console.log("Engine started:", stdout);
      return { success: true };
    } catch (error) {
      console.error("Failed to start engine:", error);
      return { success: false, error: error.message };
    }
  }
  /**
   * Stop the Coding Engine Docker stack
   */
  async stopEngine() {
    try {
      const composeFile = path.join(this.engineRoot, "infra", "docker", "docker-compose.dashboard.yml");
      await execAsync$1(
        `docker-compose -f "${composeFile}" down`,
        { cwd: this.engineRoot }
      );
      this.engineRunning = false;
      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  }
  /**
   * Get Engine status
   */
  async getEngineStatus() {
    try {
      const { stdout } = await execAsync$1('docker ps --format "{{.Names}}"');
      const services = stdout.trim().split("\n").filter(
        (name) => name.includes("coding-engine") || name.includes("postgres") || name.includes("redis")
      );
      return { running: services.length > 0, services };
    } catch {
      return { running: false, services: [] };
    }
  }
  /**
   * Start a project container with VNC for live preview
   * Automatically detects if code exists in requirementsPath or outputDir
   */
  async startProjectContainer(projectId, requirementsPath, outputDir, vncPort, appPort) {
    try {
      const containerName = sanitizeContainerName(`project-${projectId}`);
      const existing = this.containers.get(projectId);
      if (existing && existing.status === "running") {
        return { success: true, vncPort: existing.vncPort, appPort: existing.appPort };
      }
      await this.stopProjectContainer(projectId);
      await this.stopContainersByPort(vncPort);
      await this.stopContainersByPort(appPort);
      const isExistingProject = await this.fileExists(path.join(requirementsPath, "app")) || await this.fileExists(path.join(requirementsPath, "package.json")) || await this.fileExists(path.join(requirementsPath, "requirements.txt"));
      const mountPath = path.resolve(isExistingProject ? requirementsPath : outputDir);
      console.log(`[Project] Mount path: ${mountPath} (existing project: ${isExistingProject})`);
      const dockerCmd = [
        "docker",
        "run",
        "-d",
        "--name",
        containerName,
        "-v",
        `${mountPath}:/app`,
        "-p",
        `${vncPort}:6080`,
        "-p",
        `${appPort}:5173`,
        "-e",
        "ENABLE_VNC=true",
        "-e",
        "NODE_ENV=development",
        "coding-engine/sandbox:latest",
        // IMPORTANT: Use //bin/bash with double slash to prevent Git Bash from mangling
        // the path to C:/Program Files/Git/usr/bin/bash on Windows
        "//bin/bash",
        "-c",
        "//usr/local/bin/sandbox-entrypoint.sh test"
      ];
      const { stdout: containerId } = await new Promise((resolve2, reject) => {
        const proc = child_process.spawn(dockerCmd[0], dockerCmd.slice(1), {
          shell: false,
          windowsHide: true,
          env: { ...process.env, MSYS_NO_PATHCONV: "1", MSYS2_ARG_CONV_EXCL: "*" }
        });
        let stdout = "";
        let stderr = "";
        proc.stdout?.on("data", (data) => {
          stdout += data.toString();
        });
        proc.stderr?.on("data", (data) => {
          stderr += data.toString();
        });
        proc.on("close", (code) => {
          if (code === 0) {
            resolve2({ stdout });
          } else {
            reject(new Error(`Docker failed: ${stderr || stdout}`));
          }
        });
        proc.on("error", reject);
      });
      this.containers.set(projectId, {
        id: containerId.trim(),
        name: containerName,
        process: null,
        vncPort,
        appPort,
        status: "running"
      });
      console.log(`[Project] Started container ${containerName} with VNC on port ${vncPort}`);
      return { success: true, vncPort, appPort };
    } catch (error) {
      console.error(`[Project] Failed to start container for ${projectId}:`, error);
      return { success: false, error: error.message };
    }
  }
  /**
   * Stop a project container
   */
  async stopProjectContainer(projectId) {
    try {
      const containerName = sanitizeContainerName(`project-${projectId}`);
      try {
        await execAsync$1(`docker rm -f ${containerName}`);
      } catch {
      }
      this.containers.delete(projectId);
      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  }
  /**
   * Stop any containers using a specific port
   * This prevents "port already allocated" errors when starting new containers
   */
  async stopContainersByPort(port) {
    try {
      const { stdout } = await execAsync$1(`docker ps -q --filter "publish=${port}"`);
      const containerIds = stdout.trim().split("\n").filter((id) => id);
      for (const containerId of containerIds) {
        try {
          console.log(`[Docker] Stopping container ${containerId} using port ${port}`);
          await execAsync$1(`docker rm -f ${containerId}`);
        } catch {
        }
      }
      if (containerIds.length > 0) {
        console.log(`[Docker] Waiting for port ${port} to be released...`);
        await new Promise((resolve2) => setTimeout(resolve2, 1e3));
      }
    } catch {
    }
  }
  /**
   * Kill host processes (not Docker containers) using a specific port.
   * On Windows, uses PowerShell to find and terminate processes.
   * This is needed because stopContainersByPort only stops Docker containers,
   * but Node.js dev servers spawned directly on the host also hold ports.
   */
  async killHostProcessOnPort(port) {
    try {
      const findCmd = `powershell -Command "Get-NetTCPConnection -LocalPort ${port} -ErrorAction SilentlyContinue | Select-Object -ExpandProperty OwningProcess"`;
      const { stdout } = await execAsync$1(findCmd);
      const pids = stdout.trim().split("\n").filter((pid) => pid && pid.trim() !== "" && pid.trim() !== "0");
      for (const pid of pids) {
        const trimmedPid = pid.trim();
        try {
          console.log(`[Docker] Killing host process ${trimmedPid} using port ${port}`);
          await execAsync$1(`powershell -Command "Stop-Process -Id ${trimmedPid} -Force -ErrorAction SilentlyContinue"`);
        } catch {
        }
      }
      if (pids.length > 0) {
        console.log(`[Docker] Waiting for port ${port} to be released...`);
        await new Promise((resolve2) => setTimeout(resolve2, 1e3));
      }
    } catch {
    }
  }
  /**
   * Stop all generation containers matching a pattern (by name prefix)
   * More reliable than port-based cleanup for cases with encoding issues
   */
  async stopGenerationContainersByPattern(pattern) {
    try {
      const { stdout } = await execAsync$1(`docker ps --format "{{.Names}}" --filter "name=${pattern}"`);
      const containers = stdout.trim().split("\n").filter((name) => name);
      for (const containerName of containers) {
        try {
          console.log(`[Docker] Stopping container by pattern: ${containerName}`);
          await execAsync$1(`docker rm -f ${containerName}`);
        } catch {
        }
      }
      if (containers.length > 0) {
        console.log(`[Docker] Waiting for containers to release ports...`);
        await new Promise((resolve2) => setTimeout(resolve2, 1e3));
      }
    } catch {
    }
  }
  /**
   * Get project container status
   */
  async getProjectStatus(projectId) {
    const containerName = sanitizeContainerName(`project-${projectId}`);
    try {
      const { stdout } = await execAsync$1(
        `docker inspect --format='{{.State.Status}}' ${containerName}`
      );
      const status = stdout.trim();
      const info = this.containers.get(projectId);
      return {
        running: status === "running",
        vncPort: info?.vncPort,
        appPort: info?.appPort,
        health: status
      };
    } catch {
      return { running: false };
    }
  }
  /**
   * Get container logs
   */
  async getProjectLogs(projectId, tail = 100) {
    const containerName = sanitizeContainerName(`project-${projectId}`);
    try {
      const { stdout } = await execAsync$1(`docker logs --tail ${tail} ${containerName}`);
      return stdout;
    } catch (error) {
      return `Error fetching logs: ${error.message}`;
    }
  }
  /**
   * Start a code generation job (legacy - without VNC preview)
   */
  async startGeneration(requirementsPath, outputDir) {
    try {
      const cmd = `python run_society_hybrid.py "${requirementsPath}" --output-dir "${outputDir}" --fast`;
      const childProcess = child_process.spawn("python", [
        "run_society_hybrid.py",
        requirementsPath,
        "--output-dir",
        outputDir,
        "--fast"
      ], {
        cwd: this.engineRoot,
        detached: true,
        stdio: "ignore",
        shell: true,
        env: { ...global.process.env }
      });
      childProcess.unref();
      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  }
  /**
   * Start code generation WITH VNC preview container
   *
   * This is the main method for the Electron dashboard:
   * 1. Starts a VNC-enabled sandbox container with the output directory mounted
   * 2. Starts the Python generation process which writes to the output directory
   * 3. The container watches for changes and serves the app via VNC
   *
   * The user can see the app being built in real-time via the embedded VNC viewer.
   *
   * @param forceGenerate - If true, always run code generation even if project files exist.
   *                        Use this for orchestrator projects where we want to regenerate.
   */
  async startGenerationWithPreview(projectId, requirementsPath, outputDir, vncPort, appPort, forceGenerate = false) {
    try {
      console.log(`[Generation] Starting with VNC preview for project ${projectId}`);
      console.log(`[Generation] Requirements: ${requirementsPath}`);
      console.log(`[Generation] Output: ${outputDir}`);
      console.log(`[Generation] VNC Port: ${vncPort}, App Port: ${appPort}`);
      const timestamp = Date.now().toString(36);
      const sanitizedProjectId = sanitizeContainerName(projectId);
      const containerName = sanitizeContainerName(`generation-${projectId}-${timestamp}`);
      console.log(`[Docker] Sanitized container name: ${containerName}`);
      const projectPattern = `generation-${sanitizedProjectId}`;
      await this.stopGenerationContainersByPattern(projectPattern);
      await this.stopGenerationContainersByPattern("generation-");
      await this.stopContainersByPort(vncPort);
      await this.stopContainersByPort(appPort);
      await this.stopContainersByPort(appPort + 1);
      await this.killHostProcessOnPort(vncPort);
      await this.killHostProcessOnPort(appPort);
      await this.killHostProcessOnPort(appPort + 1);
      console.log("[Docker] Waiting for all ports to be released...");
      await new Promise((resolve2) => setTimeout(resolve2, 3e3));
      const sandboxDockerfile = path.join(this.engineRoot, "infra", "docker", "Dockerfile.sandbox");
      const sandboxEntrypoint = path.join(this.engineRoot, "infra", "docker", "sandbox-entrypoint.sh");
      try {
        await execAsync$1("docker image inspect coding-engine/sandbox:latest");
      } catch {
        console.log("[Generation] Building sandbox image...");
        await execAsync$1(
          `docker build -t coding-engine/sandbox:latest -f "${sandboxDockerfile}" "${path.join(this.engineRoot, "infra", "docker")}"`,
          { cwd: this.engineRoot }
        );
      }
      const hasExistingCode = await this.fileExists(path.join(requirementsPath, "app")) || await this.fileExists(path.join(requirementsPath, "src")) || await this.fileExists(path.join(requirementsPath, "package.json"));
      let isExistingProject = hasExistingCode;
      let actualRequirementsPath = requirementsPath;
      if (forceGenerate) {
        isExistingProject = false;
        const nestedReqs = path.join(requirementsPath, "docs", "requirements", "imported_requirements.json");
        const rootReqs = path.join(requirementsPath, "requirements.json");
        if (await this.fileExists(nestedReqs)) {
          actualRequirementsPath = nestedReqs;
          console.log(`[VNC] forceGenerate=true, using nested requirements: ${nestedReqs}`);
        } else if (await this.fileExists(rootReqs)) {
          actualRequirementsPath = rootReqs;
          console.log(`[VNC] forceGenerate=true, using root requirements: ${rootReqs}`);
        } else {
          console.log(`[VNC] forceGenerate=true, using path as requirements: ${requirementsPath}`);
        }
      }
      console.log(`[VNC] forceGenerate: ${forceGenerate}, hasExistingCode: ${hasExistingCode}, isExistingProject: ${isExistingProject}`);
      const mountPath = path.resolve(isExistingProject ? requirementsPath : outputDir);
      console.log(`[VNC] Mount path: ${mountPath} (existing project: ${isExistingProject})`);
      let bashScript;
      if (isExistingProject) {
        bashScript = 'echo "Starting existing project..." && //usr/local/bin/sandbox-entrypoint.sh test';
      } else {
        bashScript = 'echo "Waiting for generated files..." && while [ ! -f //app/package.json ] && [ ! -f //app/requirements.txt ]; do sleep 2; done && echo "Files detected, starting sandbox..." && //usr/local/bin/sandbox-entrypoint.sh test';
      }
      const hasPythonReqs = await this.fileExists(path.join(mountPath, "requirements.txt"));
      const hasPackageJson = await this.fileExists(path.join(mountPath, "package.json"));
      let isNodeFullstack = false;
      if (hasPackageJson && !hasPythonReqs) {
        try {
          const pkgJson = require("fs").readFileSync(path.join(mountPath, "package.json"), "utf-8");
          const hasExpress = pkgJson.includes('"express"') || pkgJson.includes('"fastify"');
          const hasVite = pkgJson.includes('"vite"') || pkgJson.includes('"react"');
          isNodeFullstack = hasExpress && hasVite;
        } catch {
        }
      }
      const isFullstack = hasPackageJson && hasPythonReqs;
      const isPythonOnly = hasPythonReqs && !hasPackageJson;
      const projectType = isFullstack ? "fullstack" : isNodeFullstack ? "node_fullstack" : isPythonOnly ? "python_fastapi" : hasPackageJson ? "react" : "auto";
      console.log(`[VNC] Detected project type: ${projectType} (fullstack: ${isFullstack}, nodeFullstack: ${isNodeFullstack})`);
      const portMappings = isFullstack ? ["-p", `${appPort}:5173`, "-p", `${appPort + 1}:8000`] : isPythonOnly ? ["-p", `${appPort}:8000`] : ["-p", `${appPort}:5173`];
      const dockerCmd = [
        "docker",
        "run",
        "-d",
        "--name",
        containerName,
        "-v",
        `${mountPath}:/app`,
        "-p",
        `${vncPort}:6080`,
        ...portMappings,
        "-e",
        "ENABLE_VNC=true",
        "-e",
        "NODE_ENV=development",
        "-e",
        `PROJECT_TYPE=${projectType}`,
        "-e",
        `PROJECT_ID=${projectId}`,
        "-e",
        `CONTAINER_NAME=${containerName}`,
        // Engine API URL for error reporting (host.docker.internal resolves to host machine)
        "-e",
        "ENGINE_API_URL=http://host.docker.internal:8000",
        "coding-engine/sandbox:latest",
        // IMPORTANT: Use //bin/bash with double slash to prevent Git Bash from mangling
        // the path to C:/Program Files/Git/usr/bin/bash on Windows
        "//bin/bash",
        "-c",
        bashScript
      ];
      let containerId = "";
      const maxRetries = 3;
      for (let attempt = 0; attempt < maxRetries; attempt++) {
        try {
          const result = await new Promise((resolve2, reject) => {
            const proc = child_process.spawn(dockerCmd[0], dockerCmd.slice(1), {
              shell: false,
              windowsHide: true,
              env: { ...process.env, MSYS_NO_PATHCONV: "1", MSYS2_ARG_CONV_EXCL: "*" }
            });
            let stdout = "";
            let stderr = "";
            proc.stdout?.on("data", (data) => {
              stdout += data.toString();
            });
            proc.stderr?.on("data", (data) => {
              stderr += data.toString();
            });
            proc.on("close", (code) => {
              if (code === 0) {
                resolve2({ stdout });
              } else {
                reject(new Error(`Docker failed: ${stderr || stdout}`));
              }
            });
            proc.on("error", reject);
          });
          containerId = result.stdout;
          break;
        } catch (error) {
          const errorMsg = error.message || "";
          if (errorMsg.includes("port") && (errorMsg.includes("not available") || errorMsg.includes("already allocated")) && attempt < maxRetries - 1) {
            console.log(`[Docker] Port conflict on attempt ${attempt + 1}, retrying in 3s...`);
            await this.killHostProcessOnPort(vncPort);
            await this.killHostProcessOnPort(appPort);
            await this.killHostProcessOnPort(appPort + 1);
            await this.stopContainersByPort(vncPort);
            await this.stopContainersByPort(appPort);
            await this.stopContainersByPort(appPort + 1);
            await new Promise((resolve2) => setTimeout(resolve2, 3e3));
          } else {
            throw error;
          }
        }
      }
      this.containers.set(projectId, {
        id: containerId.trim(),
        name: containerName,
        process: null,
        vncPort,
        appPort,
        status: "starting"
      });
      console.log(`[VNC] Container ${containerName} started`);
      let processPid;
      if (isExistingProject) {
        console.log(`[VNC] Existing project from ${requirementsPath} - entrypoint handling startup`);
        const container = this.containers.get(projectId);
        if (container) {
          container.status = "running";
        }
      } else {
        console.log(`[VNC] Generating new code from ${requirementsPath}`);
        if (!fs.existsSync(outputDir)) {
          const { mkdirSync } = require("fs");
          mkdirSync(outputDir, { recursive: true });
          console.log(`[Generation] Created output directory: ${outputDir}`);
        }
        const checkpointFile = path.join(outputDir, ".generation_checkpoint.json");
        if (fs.existsSync(checkpointFile)) {
          const { unlinkSync } = require("fs");
          unlinkSync(checkpointFile);
          console.log(`[Generation] Cleared stale checkpoint for fresh generation`);
        }
        try {
          console.log(`[Git] Initializing git repo in ${outputDir}`);
          await execAsync$1(`git init`, { cwd: outputDir });
          const { mkdirSync, writeFileSync, unlinkSync: fsUnlink, readdirSync } = require("fs");
          const cleanupNulFiles = (dir) => {
            try {
              const entries = readdirSync(dir, { withFileTypes: true });
              for (const entry of entries) {
                const fullPath = path.join(dir, entry.name);
                if (entry.isFile() && entry.name === "nul") {
                  console.log(`[Git] Removing stale 'nul' file: ${fullPath}`);
                  try {
                    fsUnlink(fullPath);
                  } catch {
                  }
                } else if (entry.isDirectory() && !["node_modules", ".git"].includes(entry.name)) {
                  cleanupNulFiles(fullPath);
                }
              }
            } catch {
            }
          };
          cleanupNulFiles(outputDir);
          const claudeMd = `# Claude Instructions for ${projectId}

## Project Overview
This project was generated by the Coding Engine.

## Key Files
- Check package.json for dependencies
- Check src/ for source code

## Build Commands
\`\`\`bash
npm install
npm run dev
\`\`\`
`;
          writeFileSync(path.join(outputDir, "CLAUDE.md"), claudeMd);
          console.log(`[Git] Created CLAUDE.md at project root`);
          const gitignorePath = path.join(outputDir, ".gitignore");
          if (!fs.existsSync(gitignorePath)) {
            const gitignoreContent = `# Dependencies
node_modules/
.pnpm-store/

# Build outputs
dist/
build/
out/

# Environment
.env
.env.local
.env.*.local

# IDE
.idea/
.vscode/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Windows shell artifacts
nul
`;
            writeFileSync(gitignorePath, gitignoreContent);
            console.log(`[Git] Created .gitignore`);
          }
          await execAsync$1(`git config --global --add safe.directory "${outputDir.replace(/\\/g, "/")}"`, { cwd: outputDir });
          await execAsync$1(`git add -A && git commit -m "Initial scaffold (auto-generated)" --allow-empty`, { cwd: outputDir });
          console.log(`[Git] Initial commit created`);
        } catch (gitError) {
          console.warn(`[Git] Warning: ${gitError.message}`);
        }
        console.log(`[Generation] Spawning with requirements: ${actualRequirementsPath}`);
        const generationProcess = child_process.spawn("python", [
          "run_society_hybrid.py",
          actualRequirementsPath,
          "--output-dir",
          outputDir,
          "--fast",
          "--no-preview",
          "--continuous-sandbox",
          // Enable DeploymentTeam continuous test cycles
          "--enable-continuous-debug"
          // Enable ContinuousDebugAgent for auto-fixing
        ], {
          cwd: this.engineRoot,
          detached: false,
          stdio: ["ignore", "pipe", "pipe"],
          shell: true,
          env: (() => {
            const env = { ...process.env };
            delete env.CLAUDECODE;
            return env;
          })()
        });
        processPid = generationProcess.pid;
        generationProcess.stdout?.on("data", (data) => {
          console.log(`[Generation] ${data.toString().trim()}`);
        });
        generationProcess.stderr?.on("data", (data) => {
          console.error(`[Generation] ${data.toString().trim()}`);
        });
        generationProcess.on("exit", (code) => {
          console.log(`[Generation] Process exited with code ${code}`);
          const container2 = this.containers.get(projectId);
          if (container2) {
            container2.status = code === 0 ? "running" : "error";
          }
        });
        const container = this.containers.get(projectId);
        if (container) {
          container.process = generationProcess;
          container.status = "running";
        }
      }
      return {
        success: true,
        vncPort,
        appPort,
        generationPid: processPid
      };
    } catch (error) {
      console.error(`[Generation] Failed:`, error);
      return { success: false, error: error.message };
    }
  }
  /**
   * Stop a generation (container + process)
   */
  async stopGeneration(projectId) {
    try {
      const container = this.containers.get(projectId);
      if (container?.process && !container.process.killed) {
        container.process.kill("SIGTERM");
      }
      if (container?.name) {
        try {
          await execAsync$1(`docker rm -f ${container.name}`);
        } catch {
        }
      }
      const sanitizedProjectId = sanitizeContainerName(projectId);
      await this.stopGenerationContainersByPattern(`generation-${sanitizedProjectId}`);
      this.containers.delete(projectId);
      return { success: true };
    } catch (error) {
      return { success: false, error: error.message };
    }
  }
  /**
   * Stop all containers on app quit
   * This is called when the Electron app is closing
   */
  async stopAllContainers() {
    console.log("[Docker] Stopping all containers...");
    const stopPromises = Array.from(this.containers.keys()).map(async (id) => {
      try {
        await this.stopGeneration(id);
      } catch {
      }
      try {
        await this.stopProjectContainer(id);
      } catch {
      }
    });
    await Promise.all(stopPromises);
    console.log("[Docker] Cleaning up orphaned containers...");
    await this.stopGenerationContainersByPattern("generation-");
    await this.stopGenerationContainersByPattern("project-");
    console.log("[Docker] All containers stopped");
  }
}
const execAsync = util.promisify(child_process.exec);
class PortAllocator {
  vncBasePort = 6081;
  appBasePort = 3001;
  maxPorts = 20;
  allocations = /* @__PURE__ */ new Map();
  usedVncPorts = /* @__PURE__ */ new Set();
  usedAppPorts = /* @__PURE__ */ new Set();
  /**
   * Allocate a VNC port for a project
   */
  async allocate(projectId) {
    const existing = this.allocations.get(projectId);
    if (existing) {
      return existing.vncPort;
    }
    const vncPort = await this.findNextPort(this.vncBasePort, this.usedVncPorts);
    this.usedVncPorts.add(vncPort);
    this.allocations.set(projectId, { vncPort, appPort: 0 });
    return vncPort;
  }
  /**
   * Allocate an app port for a project
   */
  async allocateAppPort(projectId) {
    const existing = this.allocations.get(projectId);
    if (existing && existing.appPort > 0) {
      return existing.appPort;
    }
    const appPort = await this.findNextPort(this.appBasePort, this.usedAppPorts);
    this.usedAppPorts.add(appPort);
    if (existing) {
      existing.appPort = appPort;
    } else {
      this.allocations.set(projectId, { vncPort: 0, appPort });
    }
    return appPort;
  }
  /**
   * Release ports for a project
   */
  release(projectId) {
    const allocation = this.allocations.get(projectId);
    if (allocation) {
      this.usedVncPorts.delete(allocation.vncPort);
      this.usedAppPorts.delete(allocation.appPort);
      this.allocations.delete(projectId);
    }
  }
  /**
   * Get VNC port for a project
   */
  getVncPort(projectId) {
    return this.allocations.get(projectId)?.vncPort;
  }
  /**
   * Get app port for a project
   */
  getAppPort(projectId) {
    return this.allocations.get(projectId)?.appPort;
  }
  /**
   * Get all port allocations
   */
  getAllAllocations() {
    return new Map(this.allocations);
  }
  /**
   * Check if a port is actually free on the OS by attempting to bind to it.
   */
  isPortFreeOnOS(port) {
    return new Promise((resolve) => {
      const server = net__namespace.createServer();
      server.once("error", () => resolve(false));
      server.once("listening", () => {
        server.close(() => resolve(true));
      });
      server.listen(port, "0.0.0.0");
    });
  }
  /**
   * Find next available port (checks both internal tracking and OS-level availability)
   */
  async findNextPort(basePort, usedPorts) {
    for (let i = 0; i < this.maxPorts; i++) {
      const port = basePort + i;
      if (usedPorts.has(port)) continue;
      if (await this.isPortFreeOnOS(port)) {
        return port;
      }
      console.log(`[PortAllocator] Port ${port} is in use on OS, skipping`);
    }
    throw new Error(`No available ports in range ${basePort}-${basePort + this.maxPorts}`);
  }
  /**
   * Check if a specific port is available
   */
  isPortAvailable(port) {
    return !this.usedVncPorts.has(port) && !this.usedAppPorts.has(port);
  }
  /**
   * Sync port allocations with running Docker containers
   * Call this on app startup to detect containers from previous sessions
   */
  async syncWithDocker() {
    try {
      const { stdout } = await execAsync(
        'docker ps --format "{{.Names}}|{{.Ports}}"'
      );
      for (const line of stdout.split("\n").filter(Boolean)) {
        const [name, ports] = line.split("|");
        if (!name.startsWith("generation-") && !name.startsWith("project-")) {
          continue;
        }
        const vncMatch = ports?.match(/0\.0\.0\.0:(\d+)->6080/);
        const appMatch = ports?.match(/0\.0\.0\.0:(\d+)->5173/);
        if (vncMatch) {
          const vncPort = parseInt(vncMatch[1]);
          this.usedVncPorts.add(vncPort);
        }
        if (appMatch) {
          const appPort = parseInt(appMatch[1]);
          this.usedAppPorts.add(appPort);
        }
        const projectId = name.replace(/^(generation-|project-)/, "");
        if (vncMatch || appMatch) {
          this.allocations.set(projectId, {
            vncPort: vncMatch ? parseInt(vncMatch[1]) : 0,
            appPort: appMatch ? parseInt(appMatch[1]) : 0
          });
        }
      }
      console.log(`[PortAllocator] Synced with Docker: ${this.usedVncPorts.size} VNC ports, ${this.usedAppPorts.size} app ports in use`);
    } catch (error) {
      console.log("[PortAllocator] No existing containers found");
    }
  }
  /**
   * Cleanup all stale generation/project containers
   * Call this on app startup to ensure clean state
   */
  async cleanupStaleContainers() {
    try {
      const { stdout } = await execAsync(
        'docker ps -a --format "{{.Names}}"'
      );
      const containers = stdout.split("\n").filter((name) => name.startsWith("generation-") || name.startsWith("project-"));
      for (const name of containers) {
        console.log(`[PortAllocator] Removing stale container: ${name}`);
        try {
          await execAsync(`docker rm -f ${name}`);
        } catch {
        }
      }
      this.allocations.clear();
      this.usedVncPorts.clear();
      this.usedAppPorts.clear();
      console.log(`[PortAllocator] Cleaned up ${containers.length} stale containers`);
    } catch {
      console.log("[PortAllocator] No stale containers to clean");
    }
  }
}
class ServiceManager {
  fastApiProcess = null;
  fastApiStatus = { name: "FastAPI", status: "stopped" };
  dockerStatus = { name: "Docker", status: "stopped" };
  pythonStatus = { name: "Python", status: "stopped" };
  engineRoot;
  apiPort;
  healthCheckInterval = null;
  mainWindow = null;
  constructor(engineRoot2, apiPort = 8e3) {
    this.engineRoot = engineRoot2;
    this.apiPort = apiPort;
  }
  setMainWindow(win) {
    this.mainWindow = win;
  }
  /**
   * Start all services in order:
   * 1. Check Python availability
   * 2. Check Docker availability
   * 3. Start FastAPI server
   */
  async startAll() {
    console.log("[ServiceManager] Starting all services...");
    this.pythonStatus = this.checkPython();
    this.broadcastStatus();
    this.dockerStatus = this.checkDocker();
    this.broadcastStatus();
    if (this.pythonStatus.status === "running") {
      await this.startFastAPI();
    } else {
      this.fastApiStatus = {
        name: "FastAPI",
        status: "error",
        error: "Python not available — cannot start FastAPI server"
      };
    }
    this.broadcastStatus();
    this.startHealthMonitor();
    return this.getAllStatus();
  }
  /**
   * Stop all managed services
   */
  async stopAll() {
    console.log("[ServiceManager] Stopping all services...");
    if (this.healthCheckInterval) {
      clearInterval(this.healthCheckInterval);
      this.healthCheckInterval = null;
    }
    await this.stopFastAPI();
  }
  /**
   * Get status of all services
   */
  getAllStatus() {
    return {
      fastapi: { ...this.fastApiStatus },
      docker: { ...this.dockerStatus },
      python: { ...this.pythonStatus }
    };
  }
  // ── Python Check ──────────────────────────────────────────────────────
  checkPython() {
    try {
      const version = child_process.execSync("python --version", {
        encoding: "utf-8",
        stdio: "pipe",
        cwd: this.engineRoot
      }).trim();
      console.log(`[ServiceManager] Python found: ${version}`);
      return { name: "Python", status: "running", error: void 0 };
    } catch {
      try {
        const version = child_process.execSync("python3 --version", {
          encoding: "utf-8",
          stdio: "pipe",
          cwd: this.engineRoot
        }).trim();
        console.log(`[ServiceManager] Python3 found: ${version}`);
        return { name: "Python", status: "running", error: void 0 };
      } catch {
        console.error("[ServiceManager] Python not found");
        return {
          name: "Python",
          status: "error",
          error: "Python not found in PATH. Install Python 3.11+ and add to PATH."
        };
      }
    }
  }
  // ── Docker Check ──────────────────────────────────────────────────────
  checkDocker() {
    try {
      child_process.execSync("docker info", { encoding: "utf-8", stdio: "pipe" });
      console.log("[ServiceManager] Docker is running");
      return { name: "Docker", status: "running" };
    } catch {
      console.warn("[ServiceManager] Docker not accessible");
      return {
        name: "Docker",
        status: "error",
        error: "Docker Desktop is not running. Start Docker Desktop for VNC preview and sandbox features."
      };
    }
  }
  // ── FastAPI ───────────────────────────────────────────────────────────
  async startFastAPI() {
    const alreadyRunning = await this.checkFastAPIHealth();
    if (alreadyRunning) {
      console.log("[ServiceManager] FastAPI already running on port", this.apiPort);
      this.fastApiStatus = {
        name: "FastAPI",
        status: "running",
        url: `http://localhost:${this.apiPort}`,
        upSince: (/* @__PURE__ */ new Date()).toISOString()
      };
      return;
    }
    const pythonCmd = this.getPythonCommand();
    if (!pythonCmd) {
      this.fastApiStatus = {
        name: "FastAPI",
        status: "error",
        error: "Python not available"
      };
      return;
    }
    console.log(`[ServiceManager] Starting FastAPI on port ${this.apiPort}...`);
    this.fastApiStatus = { name: "FastAPI", status: "starting" };
    this.broadcastStatus();
    try {
      this.fastApiProcess = child_process.spawn(
        pythonCmd,
        [
          "-m",
          "uvicorn",
          "src.api.main:app",
          "--host",
          "0.0.0.0",
          "--port",
          String(this.apiPort)
        ],
        {
          cwd: this.engineRoot,
          env: {
            ...process.env,
            PYTHONUNBUFFERED: "1",
            // Force unbuffered output
            PYTHONIOENCODING: "utf-8"
          },
          stdio: ["ignore", "pipe", "pipe"],
          // On Windows, don't create a console window
          windowsHide: true
        }
      );
      const pid = this.fastApiProcess.pid;
      console.log(`[ServiceManager] FastAPI process spawned with PID ${pid}`);
      this.fastApiProcess.stdout?.on("data", (data) => {
        try {
          const msg = data.toString("utf-8").trim();
          if (msg) {
            console.log(`[FastAPI] ${msg}`);
          }
        } catch {
        }
      });
      this.fastApiProcess.stdout?.on("error", () => {
      });
      this.fastApiProcess.stderr?.on("data", (data) => {
        try {
          const msg = data.toString("utf-8").trim();
          if (msg) {
            console.error(`[FastAPI:err] ${msg}`);
          }
        } catch {
        }
      });
      this.fastApiProcess.stderr?.on("error", () => {
      });
      this.fastApiProcess.on("exit", (code, signal) => {
        console.log(`[ServiceManager] FastAPI exited with code=${code} signal=${signal}`);
        this.fastApiProcess = null;
        if (this.fastApiStatus.status !== "stopped") {
          this.fastApiStatus = {
            name: "FastAPI",
            status: "error",
            error: `Process exited unexpectedly (code=${code})`
          };
          this.broadcastStatus();
        }
      });
      this.fastApiProcess.on("error", (err) => {
        console.error("[ServiceManager] FastAPI spawn error:", err);
        this.fastApiProcess = null;
        this.fastApiStatus = {
          name: "FastAPI",
          status: "error",
          error: `Failed to start: ${err.message}`
        };
        this.broadcastStatus();
      });
      const ready = await this.waitForFastAPI(3e4);
      if (ready) {
        this.fastApiStatus = {
          name: "FastAPI",
          status: "running",
          url: `http://localhost:${this.apiPort}`,
          pid,
          upSince: (/* @__PURE__ */ new Date()).toISOString()
        };
        console.log("[ServiceManager] FastAPI is ready!");
      } else {
        this.fastApiStatus = {
          name: "FastAPI",
          status: "error",
          pid,
          error: "FastAPI did not become ready within 30 seconds"
        };
        console.error("[ServiceManager] FastAPI failed to become ready");
      }
    } catch (err) {
      console.error("[ServiceManager] Failed to start FastAPI:", err);
      this.fastApiStatus = {
        name: "FastAPI",
        status: "error",
        error: err.message
      };
    }
  }
  async stopFastAPI() {
    if (this.fastApiProcess) {
      console.log("[ServiceManager] Stopping FastAPI...");
      this.fastApiStatus = { name: "FastAPI", status: "stopped" };
      try {
        if (process.platform === "win32" && this.fastApiProcess.pid) {
          child_process.execSync(`taskkill /PID ${this.fastApiProcess.pid} /T /F`, {
            stdio: "pipe"
          });
        } else {
          this.fastApiProcess.kill("SIGTERM");
        }
      } catch (err) {
        console.warn("[ServiceManager] Error killing FastAPI process:", err);
      }
      this.fastApiProcess = null;
    }
  }
  async waitForFastAPI(timeoutMs) {
    const startTime = Date.now();
    const interval = 1e3;
    while (Date.now() - startTime < timeoutMs) {
      const healthy = await this.checkFastAPIHealth();
      if (healthy) return true;
      await this.sleep(interval);
    }
    return false;
  }
  async checkFastAPIHealth() {
    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 3e3);
      const response = await fetch(`http://127.0.0.1:${this.apiPort}/health`, {
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      if (response.ok) {
        console.log("[ServiceManager] Health check passed (200 OK)");
      }
      return response.ok;
    } catch {
      return false;
    }
  }
  // ── Health Monitor ────────────────────────────────────────────────────
  startHealthMonitor() {
    this.healthCheckInterval = setInterval(async () => {
      if (this.fastApiStatus.status === "running") {
        const healthy = await this.checkFastAPIHealth();
        if (!healthy) {
          console.warn("[ServiceManager] FastAPI health check failed — attempting restart...");
          this.fastApiStatus = {
            name: "FastAPI",
            status: "error",
            error: "Health check failed"
          };
          this.broadcastStatus();
          await this.startFastAPI();
          this.broadcastStatus();
        }
      } else if (this.fastApiStatus.status === "error" && this.fastApiProcess) {
        const healthy = await this.checkFastAPIHealth();
        if (healthy) {
          console.log("[ServiceManager] FastAPI recovered — now healthy!");
          this.fastApiStatus = {
            name: "FastAPI",
            status: "running",
            url: `http://localhost:${this.apiPort}`,
            pid: this.fastApiProcess.pid,
            upSince: (/* @__PURE__ */ new Date()).toISOString()
          };
          this.broadcastStatus();
        }
      }
      const prevDockerStatus = this.dockerStatus.status;
      this.dockerStatus = this.checkDocker();
      if (prevDockerStatus !== this.dockerStatus.status) {
        this.broadcastStatus();
      }
    }, 1e4);
  }
  // ── Helpers ───────────────────────────────────────────────────────────
  getPythonCommand() {
    try {
      const pyPath = child_process.execSync('python -c "import sys; print(sys.executable)"', {
        encoding: "utf-8",
        stdio: "pipe",
        cwd: this.engineRoot
      }).trim();
      if (pyPath && fs.existsSync(pyPath)) {
        console.log(`[ServiceManager] Resolved Python path: ${pyPath}`);
        return pyPath;
      }
      return "python";
    } catch {
      try {
        const pyPath = child_process.execSync('python3 -c "import sys; print(sys.executable)"', {
          encoding: "utf-8",
          stdio: "pipe",
          cwd: this.engineRoot
        }).trim();
        if (pyPath && fs.existsSync(pyPath)) {
          console.log(`[ServiceManager] Resolved Python3 path: ${pyPath}`);
          return pyPath;
        }
        return "python3";
      } catch {
        return null;
      }
    }
  }
  sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }
  broadcastStatus() {
    if (this.mainWindow && !this.mainWindow.isDestroyed()) {
      this.mainWindow.webContents.send("services:status-update", this.getAllStatus());
    }
  }
}
process.on("uncaughtException", (err) => {
  if (err.code === "EPIPE" || err.code === "ERR_STREAM_DESTROYED") {
    return;
  }
  console.error("[Main] Uncaught exception:", err);
  electron.dialog.showErrorBox("Unexpected Error", `${err.message}

${err.stack}`);
});
const engineRoot = path.join(__dirname, "..", "..", "..");
const envPath = path.join(engineRoot, ".env");
if (fs.existsSync(envPath)) {
  dotenv__namespace.config({ path: envPath });
  console.log("[Main] Loaded .env from:", envPath);
  console.log("[Main] ANTHROPIC_API_KEY:", process.env.ANTHROPIC_API_KEY ? "set" : "NOT SET");
} else {
  console.warn("[Main] .env not found at:", envPath);
}
function isDockerAccessible() {
  try {
    child_process.execSync("docker info", { encoding: "utf-8", stdio: "pipe" });
    return { accessible: true };
  } catch (error) {
    return {
      accessible: false,
      error: "Docker is not accessible. Please ensure Docker Desktop is running and you have permissions."
    };
  }
}
function isOrchestratorRunning() {
  try {
    const result = child_process.execSync('docker inspect --format="{{.State.Running}}" req-orchestrator', {
      encoding: "utf-8",
      stdio: "pipe"
    }).trim();
    const isRunning = result === "true" || result === '"true"';
    return { running: isRunning, exists: true };
  } catch (error) {
    return {
      running: false,
      exists: false,
      error: "The req-orchestrator container is not running.\n\nTo start it, run:\n  docker-compose -f path/to/orchestrator/docker-compose.yml up -d\n\nOr use local requirements files instead of orchestrator projects."
    };
  }
}
async function copyRequirementsFromDocker(dockerPath, engineRoot2) {
  if (!dockerPath.startsWith("/app/projects/")) {
    return dockerPath;
  }
  const dockerCheck = isDockerAccessible();
  if (!dockerCheck.accessible) {
    console.error("[Requirements] Docker not accessible:", dockerCheck.error);
    throw new Error(dockerCheck.error);
  }
  const orchestratorCheck = isOrchestratorRunning();
  if (!orchestratorCheck.exists) {
    console.error("[Requirements] req-orchestrator container not found");
    throw new Error(orchestratorCheck.error);
  }
  if (!orchestratorCheck.running) {
    console.error("[Requirements] req-orchestrator container exists but is not running");
    throw new Error(
      "The req-orchestrator container exists but is stopped.\n\nTo start it, run:\n  docker start req-orchestrator"
    );
  }
  const projectFolder = dockerPath.replace("/app/projects/", "");
  const localReqDir = path.join(engineRoot2, ".requirements-cache", projectFolder);
  if (!fs.existsSync(path.join(engineRoot2, ".requirements-cache"))) {
    fs.mkdirSync(path.join(engineRoot2, ".requirements-cache"), { recursive: true });
  }
  try {
    console.log(`[Requirements] Copying from req-orchestrator:${dockerPath} to ${localReqDir}`);
    child_process.execSync(`docker cp req-orchestrator:${dockerPath} "${localReqDir}"`, { encoding: "utf-8" });
    const reqJsonPath = path.join(localReqDir, "requirements.json");
    if (fs.existsSync(reqJsonPath)) {
      return reqJsonPath;
    }
    return localReqDir;
  } catch (error) {
    console.error(`[Requirements] Failed to copy from Docker:`, error.message);
    throw new Error(`Could not copy requirements from Docker: ${error.message}`);
  }
}
const dockerManager = new DockerManager();
const portAllocator = new PortAllocator();
const serviceManager = new ServiceManager(engineRoot, 8e3);
let mainWindow = null;
function createWindow() {
  mainWindow = new electron.BrowserWindow({
    width: 1600,
    height: 1e3,
    minWidth: 1200,
    minHeight: 800,
    webPreferences: {
      preload: path.join(__dirname, "../preload/preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false
    },
    titleBarStyle: "hiddenInset",
    backgroundColor: "#0f172a",
    show: false
  });
  mainWindow.once("ready-to-show", () => {
    mainWindow?.show();
  });
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    electron.shell.openExternal(url);
    return { action: "deny" };
  });
  if (process.env.ELECTRON_RENDERER_URL) {
    mainWindow.loadURL(process.env.ELECTRON_RENDERER_URL);
  } else {
    mainWindow.loadFile(path.join(__dirname, "../renderer/index.html"));
  }
  if (process.env.NODE_ENV === "development") {
    mainWindow.webContents.openDevTools();
  }
  mainWindow.on("closed", () => {
    mainWindow = null;
  });
}
electron.app.whenReady().then(async () => {
  await portAllocator.syncWithDocker();
  createWindow();
  if (mainWindow) {
    serviceManager.setMainWindow(mainWindow);
  }
  console.log("[App] Auto-starting backend services...");
  const serviceStatus = await serviceManager.startAll();
  console.log("[App] Service status:", JSON.stringify(serviceStatus, null, 2));
  electron.app.on("activate", () => {
    if (electron.BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});
electron.app.on("window-all-closed", async () => {
  console.log("[App] Window closed, cleaning up services and Docker containers...");
  await serviceManager.stopAll();
  await dockerManager.stopAllContainers();
  if (process.platform !== "darwin") {
    electron.app.quit();
  }
});
let isCleaningUp = false;
electron.app.on("before-quit", async (event) => {
  if (isCleaningUp) return;
  isCleaningUp = true;
  event.preventDefault();
  console.log("[App] Before quit - stopping services and Docker containers...");
  try {
    await serviceManager.stopAll();
    await dockerManager.stopAllContainers();
  } catch (error) {
    console.error("[App] Error during cleanup:", error);
  }
  electron.app.exit(0);
});
electron.ipcMain.handle("docker:start-engine", async () => {
  return await dockerManager.startEngine();
});
electron.ipcMain.handle("docker:stop-engine", async () => {
  return await dockerManager.stopEngine();
});
electron.ipcMain.handle("docker:get-engine-status", async () => {
  return await dockerManager.getEngineStatus();
});
electron.ipcMain.handle("docker:start-project", async (_, projectId, requirementsPath, outputDir) => {
  const vncPort = await portAllocator.allocate(projectId);
  const appPort = await portAllocator.allocateAppPort(projectId);
  const success = await dockerManager.startProjectContainer(projectId, requirementsPath, outputDir, vncPort, appPort);
  return { success, vncPort, appPort };
});
electron.ipcMain.handle("docker:stop-project", async (_, projectId) => {
  portAllocator.release(projectId);
  return await dockerManager.stopProjectContainer(projectId);
});
electron.ipcMain.handle("docker:get-project-status", async (_, projectId) => {
  return await dockerManager.getProjectStatus(projectId);
});
electron.ipcMain.handle("docker:get-project-logs", async (_, projectId, tail = 100) => {
  return await dockerManager.getProjectLogs(projectId, tail);
});
electron.ipcMain.handle("ports:get-vnc-port", (_, projectId) => {
  return portAllocator.getVncPort(projectId);
});
electron.ipcMain.handle("ports:get-app-port", (_, projectId) => {
  return portAllocator.getAppPort(projectId);
});
electron.ipcMain.handle("ports:get-all", () => {
  return portAllocator.getAllAllocations();
});
electron.ipcMain.handle("services:get-status", async () => {
  return serviceManager.getAllStatus();
});
electron.ipcMain.handle("services:restart-fastapi", async () => {
  console.log("[IPC] Restarting FastAPI server...");
  await serviceManager.stopAll();
  const status = await serviceManager.startAll();
  return status;
});
electron.ipcMain.handle("engine:start-generation", async (_, requirementsPath, outputDir) => {
  return await dockerManager.startGeneration(requirementsPath, outputDir);
});
electron.ipcMain.handle("engine:start-generation-with-preview", async (_, projectId, requirementsPath, outputDir, forceGenerate = false) => {
  try {
    const engineRoot2 = path.join(__dirname, "..", "..", "..");
    let localRequirementsPath = requirementsPath;
    if (requirementsPath.startsWith("/app/projects/")) {
      localRequirementsPath = await copyRequirementsFromDocker(requirementsPath, engineRoot2);
      console.log(`[Generation] Converted Docker path to local: ${localRequirementsPath}`);
    }
    const vncPort = await portAllocator.allocate(projectId);
    const appPort = await portAllocator.allocateAppPort(projectId);
    const absoluteOutputDir = outputDir.startsWith(".") ? path.join(engineRoot2, outputDir.replace(/^\.\//, "")) : outputDir;
    return await dockerManager.startGenerationWithPreview(
      projectId,
      localRequirementsPath,
      absoluteOutputDir,
      vncPort,
      appPort,
      forceGenerate
    );
  } catch (error) {
    console.error("[Generation] Error:", error);
    return { success: false, error: error.message };
  }
});
electron.ipcMain.handle("engine:stop-generation", async (_, projectId) => {
  portAllocator.release(projectId);
  return await dockerManager.stopGeneration(projectId);
});
electron.ipcMain.handle("engine:get-api-url", () => {
  return "http://localhost:8000";
});
electron.ipcMain.handle("fs:open-folder", async (_, path2) => {
  return electron.shell.openPath(path2);
});
electron.ipcMain.handle("fs:show-in-explorer", async (_, path2) => {
  electron.shell.showItemInFolder(path2);
});
electron.ipcMain.handle("fs:exists", async (_, path2) => {
  return fs.existsSync(path2);
});
const ORCHESTRATOR_API = "http://localhost:8087";
const TECHSTACK_API = `${ORCHESTRATOR_API}/api/v1/techstack`;
electron.ipcMain.handle("projects:get-all", async () => {
  try {
    const response = await fetch(`${TECHSTACK_API}/projects`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const data = await response.json();
    console.log(`[Projects] Loaded ${data.total || data.projects?.length || 0} projects from orchestrator`);
    return data.projects || [];
  } catch (error) {
    console.error("[Projects] Failed to fetch all projects:", error.message);
    return [];
  }
});
electron.ipcMain.handle("projects:get", async (_, id) => {
  try {
    const response = await fetch(`${TECHSTACK_API}/projects/${id}`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.error(`[Projects] Failed to fetch project ${id}:`, error.message);
    return null;
  }
});
electron.ipcMain.handle("projects:create", async (_, data) => {
  try {
    const response = await fetch(`${TECHSTACK_API}/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data)
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.error("[Projects] Failed to create project:", error.message);
    throw error;
  }
});
electron.ipcMain.handle("projects:delete", async (_, id) => {
  try {
    const response = await fetch(`${TECHSTACK_API}/projects/${id}`, {
      method: "DELETE"
    });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return { success: true };
  } catch (error) {
    console.error(`[Projects] Failed to delete project ${id}:`, error.message);
    throw error;
  }
});
electron.ipcMain.handle("projects:get-status", async (_, id) => {
  try {
    const response = await fetch(`${TECHSTACK_API}/projects/${id}/status`);
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.error(`[Projects] Failed to get project status ${id}:`, error.message);
    return null;
  }
});
electron.ipcMain.handle("projects:send-to-engine", async (_, projectIds) => {
  try {
    const response = await fetch(`${TECHSTACK_API}/send-to-engine`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_ids: projectIds })
    });
    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.error("[Projects] Failed to send to engine:", error.message);
    return { success: false, error: error.message };
  }
});
electron.ipcMain.handle("projects:scan-local-dirs", async (_, scanPaths) => {
  const defaultScanDir = path.join(engineRoot, "Data", "all_services");
  const dirsToScan = scanPaths && scanPaths.length > 0 ? scanPaths : [defaultScanDir];
  const results = [];
  for (const scanDir of dirsToScan) {
    if (!fs.existsSync(scanDir)) {
      console.log(`[RE] Scan directory not found: ${scanDir}`);
      continue;
    }
    let entries;
    try {
      entries = fs.readdirSync(scanDir, { withFileTypes: true });
    } catch (err) {
      console.error(`[RE] Failed to read directory ${scanDir}:`, err.message);
      continue;
    }
    for (const entry of entries) {
      if (!entry.isDirectory()) continue;
      const projectDir = path.join(scanDir, entry.name);
      const indicators = [
        path.join(projectDir, "MASTER_DOCUMENT.md"),
        path.join(projectDir, "tech_stack", "tech_stack.json"),
        path.join(projectDir, "user_stories", "user_stories.md"),
        path.join(projectDir, "content_analysis.json")
      ];
      const isREProject = indicators.some((p) => fs.existsSync(p));
      if (!isREProject) continue;
      try {
        const summary = readREProjectSummary(projectDir, entry.name);
        results.push(summary);
        console.log(`[RE] Found project: ${summary.project_name} (${summary.requirements_count} reqs, ${summary.tasks_count} tasks)`);
      } catch (err) {
        console.warn(`[RE] Failed to read project ${entry.name}:`, err.message);
      }
    }
  }
  console.log(`[RE] Scan complete: ${results.length} RE projects found`);
  return results;
});
electron.ipcMain.handle("projects:get-re-detail", async (_, projectPath) => {
  try {
    return readREProjectDetail(projectPath);
  } catch (err) {
    console.error(`[RE] Failed to read project detail:`, err.message);
    return null;
  }
});
function readREProjectSummary(projectDir, folderName) {
  let projectName = folderName;
  const techStackTags = [];
  let architecturePattern = "";
  let requirementsCount = 0;
  let userStoriesCount = 0;
  let tasksCount = 0;
  let diagramCount = 0;
  let qualityIssues = { critical: 0, high: 0, medium: 0 };
  let hasApiSpec = false;
  let hasMasterDocument = false;
  const techStackFull = {};
  const techStackPath = path.join(projectDir, "tech_stack", "tech_stack.json");
  if (fs.existsSync(techStackPath)) {
    try {
      const data = JSON.parse(fs.readFileSync(techStackPath, "utf-8"));
      const rawName = data.project_name || "";
      projectName = rawName && rawName !== "unnamed_project" ? rawName : folderName;
      architecturePattern = data.architecture_pattern || "";
      if (data.frontend_framework) techStackTags.push(data.frontend_framework);
      if (data.backend_framework) techStackTags.push(data.backend_framework);
      if (data.primary_database) techStackTags.push(data.primary_database);
      if (data.cache_layer && data.cache_layer !== "none") techStackTags.push(data.cache_layer);
      for (const [key, val] of Object.entries(data)) {
        if (typeof val === "string" && key !== "project_name") {
          techStackFull[key] = val;
        }
      }
    } catch {
    }
  }
  const userStoriesPaths = [
    path.join(projectDir, "user_stories", "user_stories.json"),
    path.join(projectDir, "user_stories.json")
  ];
  const userStoriesJsonPath = userStoriesPaths.find((p) => fs.existsSync(p)) || "";
  if (userStoriesJsonPath) {
    try {
      const data = JSON.parse(fs.readFileSync(userStoriesJsonPath, "utf-8"));
      if (Array.isArray(data)) {
        userStoriesCount = data.length;
        const reqIds = /* @__PURE__ */ new Set();
        for (const story of data) {
          if (story.linked_requirement) reqIds.add(story.linked_requirement);
        }
        requirementsCount = reqIds.size || userStoriesCount;
      }
    } catch {
    }
  }
  const taskListPath = path.join(projectDir, "tasks", "task_list.json");
  if (fs.existsSync(taskListPath)) {
    try {
      const data = JSON.parse(fs.readFileSync(taskListPath, "utf-8"));
      tasksCount = data.total_tasks || 0;
      if (!tasksCount && data.features) {
        for (const tasks of Object.values(data.features)) {
          if (Array.isArray(tasks)) tasksCount += tasks.length;
        }
      }
    } catch {
    }
  }
  const diagramsDir = path.join(projectDir, "diagrams");
  if (fs.existsSync(diagramsDir)) {
    try {
      const files = fs.readdirSync(diagramsDir);
      diagramCount = files.filter((f) => f.endsWith(".mmd") || f.endsWith(".md")).length;
    } catch {
    }
  }
  const qualityPath = path.join(projectDir, "quality", "self_critique_report.json");
  if (fs.existsSync(qualityPath)) {
    try {
      const data = JSON.parse(fs.readFileSync(qualityPath, "utf-8"));
      const bySeverity = data.summary?.by_severity || {};
      qualityIssues = {
        critical: bySeverity.critical || 0,
        high: bySeverity.high || 0,
        medium: bySeverity.medium || 0
      };
    } catch {
    }
  }
  hasApiSpec = fs.existsSync(path.join(projectDir, "api", "openapi_spec.yaml")) || fs.existsSync(path.join(projectDir, "api", "api_documentation.md"));
  hasMasterDocument = fs.existsSync(path.join(projectDir, "MASTER_DOCUMENT.md"));
  return {
    project_id: folderName,
    project_name: projectName,
    project_path: projectDir,
    source: "local_re",
    tech_stack_tags: techStackTags,
    architecture_pattern: architecturePattern,
    requirements_count: requirementsCount,
    user_stories_count: userStoriesCount,
    tasks_count: tasksCount,
    diagram_count: diagramCount,
    quality_issues: qualityIssues,
    has_api_spec: hasApiSpec,
    has_master_document: hasMasterDocument
  };
}
function readREProjectDetail(projectDir) {
  const folderName = require("path").basename(projectDir);
  const summary = readREProjectSummary(projectDir, folderName);
  const tasksByFeature = {};
  const taskListPath = path.join(projectDir, "tasks", "task_list.json");
  if (fs.existsSync(taskListPath)) {
    try {
      const data = JSON.parse(fs.readFileSync(taskListPath, "utf-8"));
      for (const [featureId, tasks] of Object.entries(data.features || {})) {
        if (Array.isArray(tasks)) {
          tasksByFeature[featureId] = tasks.map((t) => ({
            id: t.id || "",
            title: t.title || "",
            task_type: t.task_type || "",
            complexity: t.complexity || "medium",
            estimated_hours: t.estimated_hours || 0
          }));
        }
      }
    } catch {
    }
  }
  let qualityIssuesList = [];
  const qualityPath = path.join(projectDir, "quality", "self_critique_report.json");
  if (fs.existsSync(qualityPath)) {
    try {
      const data = JSON.parse(fs.readFileSync(qualityPath, "utf-8"));
      qualityIssuesList = (data.issues || []).map((i) => ({
        id: i.id || "",
        category: i.category || "",
        severity: i.severity || "medium",
        title: i.title || ""
      }));
    } catch {
    }
  }
  let masterDocExcerpt = "";
  const masterDocPath = path.join(projectDir, "MASTER_DOCUMENT.md");
  if (fs.existsSync(masterDocPath)) {
    try {
      const content = fs.readFileSync(masterDocPath, "utf-8");
      masterDocExcerpt = content.slice(0, 2e3);
    } catch {
    }
  }
  let featureBreakdown = [];
  const fbPath = path.join(projectDir, "work_breakdown", "feature_breakdown.json");
  if (fs.existsSync(fbPath)) {
    try {
      const data = JSON.parse(fs.readFileSync(fbPath, "utf-8"));
      for (const [featId, feat] of Object.entries(data.features || {})) {
        const f = feat;
        featureBreakdown.push({
          feature_id: f.feature_id || featId,
          feature_name: f.feature_name || "",
          requirements: f.requirements || []
        });
      }
    } catch {
    }
  }
  let techStackFull = {};
  const techStackPath = path.join(projectDir, "tech_stack", "tech_stack.json");
  if (fs.existsSync(techStackPath)) {
    try {
      const data = JSON.parse(fs.readFileSync(techStackPath, "utf-8"));
      for (const [key, val] of Object.entries(data)) {
        if (typeof val === "string") techStackFull[key] = val;
      }
    } catch {
    }
  }
  return {
    ...summary,
    tech_stack_full: techStackFull,
    tasks_by_feature: tasksByFeature,
    quality_issues_list: qualityIssuesList,
    master_document_excerpt: masterDocExcerpt,
    feature_breakdown: featureBreakdown
  };
}
electron.ipcMain.handle("engine:start-orchestrator-generation-with-preview", async (_, projectId, projectPath, outputDir) => {
  try {
    const engineRoot2 = path.join(__dirname, "..", "..", "..");
    const absoluteOutputDir = outputDir.startsWith(".") ? path.join(engineRoot2, outputDir.replace(/^\.\//, "")) : outputDir;
    console.log(`[Orchestrator] Starting generation with VNC for project ${projectId}`);
    console.log(`[Orchestrator] Project path: ${projectPath}`);
    console.log(`[Orchestrator] Output dir (absolute): ${absoluteOutputDir}`);
    let localRequirementsPath = projectPath;
    if (projectPath.startsWith("/app/projects/")) {
      localRequirementsPath = await copyRequirementsFromDocker(projectPath, engineRoot2);
      console.log(`[Orchestrator] Local requirements path: ${localRequirementsPath}`);
    }
    const vncPort = await portAllocator.allocate(projectId);
    const appPort = await portAllocator.allocateAppPort(projectId);
    console.log(`[Orchestrator] Allocated ports - VNC: ${vncPort}, App: ${appPort}`);
    const containerResult = await dockerManager.startGenerationWithPreview(
      projectId,
      localRequirementsPath,
      // Use LOCAL path for Python generation
      absoluteOutputDir,
      vncPort,
      appPort,
      true
      // forceGenerate: always generate for orchestrator projects
    );
    if (!containerResult.success) {
      console.error(`[Orchestrator] Failed to start VNC container:`, containerResult.error);
      return { success: false, error: containerResult.error };
    }
    console.log(`[Orchestrator] VNC container started on port ${vncPort}`);
    try {
      const jobResponse = await fetch("http://localhost:8000/api/v1/jobs", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_id: projectId,
          project_path: projectPath,
          output_dir: outputDir,
          vnc_port: vncPort,
          app_port: appPort
        })
      });
      if (jobResponse.ok) {
        const jobData = await jobResponse.json();
        console.log(`[Orchestrator] Job registered with Coding Engine:`, jobData.id);
      }
    } catch (apiError) {
      console.warn(`[Orchestrator] Could not register job with API:`, apiError);
    }
    return {
      success: true,
      vncPort,
      appPort,
      generationPid: containerResult.generationPid
    };
  } catch (error) {
    console.error(`[Orchestrator] Generation failed:`, error);
    portAllocator.release(projectId);
    return { success: false, error: error.message };
  }
});
const ENGINE_API = process.env.ENGINE_API_URL || "http://localhost:8000";
electron.ipcMain.handle("engine:get-epics", async (_, projectPath) => {
  console.log(`[Epic:IPC] get-epics called with path: ${projectPath}`);
  try {
    const url = `${ENGINE_API}/api/v1/dashboard/epics?project_path=${encodeURIComponent(projectPath)}`;
    console.log(`[Epic:IPC] Fetching: ${url}`);
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const data = await response.json();
    console.log(`[Epic:IPC] Got ${data.epics?.length ?? 0} epics from API`);
    return data;
  } catch (error) {
    console.error("[Epic:IPC] Failed to get epics:", error.message);
    return { project_path: projectPath, total_epics: 0, epics: [] };
  }
});
electron.ipcMain.handle("engine:get-epic-tasks", async (_, epicId, projectPath) => {
  try {
    const response = await fetch(
      `${ENGINE_API}/api/v1/dashboard/epic/${epicId}/tasks?project_path=${encodeURIComponent(projectPath)}`
    );
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    console.error(`[Epic] Failed to get tasks for ${epicId}:`, error.message);
    return { epic_id: epicId, tasks: [], total_tasks: 0 };
  }
});
electron.ipcMain.handle("engine:run-epic", async (_, epicId, projectPath) => {
  try {
    const response = await fetch(`${ENGINE_API}/api/v1/dashboard/epic/${epicId}/run`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_path: projectPath })
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    console.error(`[Epic] Failed to run ${epicId}:`, error.message);
    return { success: false, error: error.message };
  }
});
electron.ipcMain.handle("engine:rerun-epic", async (_, epicId, projectPath) => {
  try {
    const response = await fetch(`${ENGINE_API}/api/v1/dashboard/epic/${epicId}/rerun`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_path: projectPath })
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    console.error(`[Epic] Failed to rerun ${epicId}:`, error.message);
    return { success: false, error: error.message };
  }
});
electron.ipcMain.handle("engine:rerun-task", async (_, epicId, taskId, projectPath, fixInstructions) => {
  try {
    const response = await fetch(`${ENGINE_API}/api/v1/dashboard/epic/${epicId}/task/${taskId}/rerun`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        project_path: projectPath,
        fix_instructions: fixInstructions || null
      })
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    console.error(`[Epic] Failed to rerun task ${taskId}:`, error.message);
    return { success: false, error: error.message };
  }
});
electron.ipcMain.handle("engine:generate-task-lists", async (_, projectPath) => {
  try {
    const response = await fetch(`${ENGINE_API}/api/v1/dashboard/generate-task-lists`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ project_path: projectPath })
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return await response.json();
  } catch (error) {
    console.error("[Epic] Failed to generate task lists:", error.message);
    return { success: false, error: error.message };
  }
});
electron.ipcMain.handle("engine:start-epic-generation", async (_, projectId, projectPath, outputDir) => {
  try {
    const engineRoot2 = path.join(__dirname, "..", "..", "..");
    const absoluteOutputDir = outputDir.startsWith(".") ? path.join(engineRoot2, outputDir.replace(/^\.\//, "")) : outputDir;
    console.log(`[EpicGen] Starting epic-based generation for ${projectId}`);
    console.log(`[EpicGen] Project path: ${projectPath}`);
    console.log(`[EpicGen] Output dir: ${absoluteOutputDir}`);
    const vncPort = await portAllocator.allocate(projectId);
    const appPort = await portAllocator.allocateAppPort(projectId);
    console.log(`[EpicGen] Allocated ports - VNC: ${vncPort}, App: ${appPort}`);
    const containerResult = await dockerManager.startProjectContainer(
      projectId,
      absoluteOutputDir,
      // Mount output dir for live preview
      absoluteOutputDir,
      vncPort,
      appPort
    );
    if (!containerResult.success) {
      console.error(`[EpicGen] Failed to start VNC container:`, containerResult.error);
      portAllocator.release(projectId);
      return { success: false, error: containerResult.error };
    }
    try {
      const response = await fetch(`${ENGINE_API}/api/v1/dashboard/start-epic-generation`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          project_path: projectPath,
          output_dir: absoluteOutputDir,
          vnc_port: vncPort,
          app_port: appPort
        })
      });
      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        console.error(`[EpicGen] FastAPI returned ${response.status}:`, errorData);
      } else {
        const data = await response.json();
        console.log(`[EpicGen] EpicOrchestrator started:`, data);
      }
    } catch (apiError) {
      console.warn(`[EpicGen] Could not start EpicOrchestrator via API:`, apiError.message);
    }
    console.log(`[EpicGen] Epic generation started on VNC port ${vncPort}`);
    return { success: true, vncPort, appPort };
  } catch (error) {
    console.error(`[EpicGen] Generation failed:`, error);
    portAllocator.release(projectId);
    return { success: false, error: error.message };
  }
});
electron.ipcMain.handle("claude:chat", async (_, payload) => {
  try {
    const apiUrl = process.env.ENGINE_API_URL || "http://localhost:8000";
    const response = await fetch(`${apiUrl}/api/v1/dashboard/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message: payload.message,
        project_path: payload.projectPath,
        output_dir: payload.outputDir,
        history: payload.conversationHistory || []
      })
    });
    if (!response.ok) {
      return {
        success: false,
        error: `API error: ${response.status} ${response.statusText}`,
        response: "",
        files_modified: [],
        files_created: []
      };
    }
    return await response.json();
  } catch (error) {
    console.error("[Claude Chat] Error:", error);
    return {
      success: false,
      error: error.message,
      response: "",
      files_modified: [],
      files_created: []
    };
  }
});
electron.ipcMain.handle("debug:get-browser-errors", async () => {
  try {
    const response = await fetch("http://localhost:8765/api/browser-errors");
    if (response.ok) {
      const data = await response.json();
      return data.errors || [];
    }
    return [];
  } catch {
    return [];
  }
});
electron.ipcMain.handle("debug:get-docker-logs", async (_, projectId, tail = 200) => {
  try {
    return await dockerManager.getProjectLogs(projectId, tail);
  } catch (error) {
    console.error("[Debug] Docker logs error:", error);
    return "";
  }
});
electron.ipcMain.handle("debug:capture-screenshot", async (_, projectId) => {
  try {
    const apiUrl = process.env.ENGINE_API_URL || "http://localhost:8000";
    const response = await fetch(`${apiUrl}/api/v1/vnc/${projectId}/screenshot`, {
      method: "POST"
    });
    if (response.ok) {
      const data = await response.json();
      return { success: true, screenshot: data.screenshot };
    }
    return { success: false, error: `Screenshot API returned ${response.status}` };
  } catch (error) {
    console.error("[Debug] Screenshot error:", error);
    return { success: false, error: error.message };
  }
});
