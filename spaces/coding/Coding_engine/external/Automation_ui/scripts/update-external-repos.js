#!/usr/bin/env node

/**
 * External Repository Update Script (Node.js)
 * Part of autonomous programmer project - maintains external dependencies
 * Author: Autonomous Agent
 * Purpose: Cross-platform alternative to PowerShell script for updating external repositories
 */

import fs from 'fs';
import path from 'path';
import { execSync } from 'child_process';
import process from 'process';
import { fileURLToPath } from 'url';
import { dirname } from 'path';

const __filename = fileURLToPath(import.meta.url);
const __dirname = dirname(__filename);

// Configuration
const CONFIG_PATH = 'config/external-repos.json';
const LOG_LEVELS = {
  INFO: 'INFO',
  WARN: 'WARN',
  ERROR: 'ERROR',
  SUCCESS: 'SUCCESS'
};

/**
 * Logging utility with timestamp and color coding
 * @param {string} message - Log message
 * @param {string} level - Log level (INFO, WARN, ERROR, SUCCESS)
 */
function writeLog(message, level = LOG_LEVELS.INFO) {
  const timestamp = new Date().toISOString().replace('T', ' ').substring(0, 19);
  const colors = {
    [LOG_LEVELS.INFO]: '\x1b[36m',    // Cyan
    [LOG_LEVELS.WARN]: '\x1b[33m',    // Yellow
    [LOG_LEVELS.ERROR]: '\x1b[31m',   // Red
    [LOG_LEVELS.SUCCESS]: '\x1b[32m'  // Green
  };
  const reset = '\x1b[0m';
  const color = colors[level] || colors[LOG_LEVELS.INFO];
  
  console.log(`${color}[${timestamp}] [${level}] ${message}${reset}`);
}

/**
 * Load and validate external repository configuration
 * @returns {Object} Configuration object
 */
function loadConfiguration() {
  try {
    if (!fs.existsSync(CONFIG_PATH)) {
      throw new Error(`Configuration file not found: ${CONFIG_PATH}`);
    }
    
    const configContent = fs.readFileSync(CONFIG_PATH, 'utf8');
    const config = JSON.parse(configContent);
    
    // Validate configuration structure
    if (!config.repositories || !Array.isArray(config.repositories)) {
      throw new Error('Invalid configuration: repositories array is required');
    }
    
    writeLog(`Loaded configuration for ${config.repositories.length} repositories`);
    return config;
  } catch (error) {
    writeLog(`Failed to load configuration: ${error.message}`, LOG_LEVELS.ERROR);
    throw error;
  }
}

/**
 * Execute git command with error handling
 * @param {string} command - Git command to execute
 * @param {string} cwd - Working directory
 * @returns {string} Command output
 */
function executeGitCommand(command, cwd = process.cwd()) {
  try {
    const result = execSync(command, {
      cwd: cwd,
      encoding: 'utf8',
      stdio: ['pipe', 'pipe', 'pipe']
    });
    return result.trim();
  } catch (error) {
    throw new Error(`Git command failed: ${command}\nError: ${error.message}`);
  }
}

/**
 * Check if directory is a git repository
 * @param {string} dirPath - Directory path to check
 * @returns {boolean} True if it's a git repository
 */
function isGitRepository(dirPath) {
  return fs.existsSync(path.join(dirPath, '.git'));
}

/**
 * Copy files matching include/exclude patterns
 * @param {string} sourceDir - Source directory
 * @param {string} targetDir - Target directory
 * @param {Array} includePatterns - Patterns to include
 * @param {Array} excludePatterns - Patterns to exclude
 */
async function copySelectiveFiles(sourceDir, targetDir, includePatterns = [], excludePatterns = []) {
  const { glob } = await import('glob');
  const { minimatch } = await import('minimatch');
  
  writeLog(`Copying files from ${sourceDir} to ${targetDir}`);
  writeLog(`Include patterns: ${JSON.stringify(includePatterns)}`);
  writeLog(`Exclude patterns: ${JSON.stringify(excludePatterns)}`);
  
  // If no include patterns specified, include everything
  const patterns = includePatterns.length > 0 ? includePatterns : ['**/*'];
  
  for (const pattern of patterns) {
    try {
      const files = await glob(pattern, { cwd: sourceDir, nodir: true });
      writeLog(`Pattern '${pattern}' matched ${files.length} files`);
      
      for (const file of files) {
        // Check if file should be excluded
        const shouldExclude = excludePatterns.some(excludePattern => {
          return minimatch(file, excludePattern);
        });
        
        if (!shouldExclude) {
          const sourcePath = path.join(sourceDir, file);
          const targetPath = path.join(targetDir, file);
          
          // Ensure target directory exists
          const targetFileDir = path.dirname(targetPath);
          if (!fs.existsSync(targetFileDir)) {
            fs.mkdirSync(targetFileDir, { recursive: true });
          }
          
          // Copy file
          fs.copyFileSync(sourcePath, targetPath);
          writeLog(`Copied: ${file}`);
        } else {
          writeLog(`Excluded: ${file}`);
        }
      }
    } catch (error) {
      writeLog(`Error processing pattern '${pattern}': ${error.message}`, LOG_LEVELS.WARN);
    }
  }
}

/**
 * Update or clone external repository with selective content filtering
 * @param {Object} repo - Repository configuration
 * @returns {Promise<boolean>} Success status
 */
async function updateExternalRepository(repo) {
  try {
    writeLog(`Processing repository: ${repo.name}`);
    writeLog(`Team: ${repo.team}`);
    writeLog(`Description: ${repo.description}`);
    
    // Check if this is a local file:// URL for selective copying
    const isLocalRepo = repo.url.startsWith('file://');
    const hasSelectivePatterns = repo.includePatterns || repo.excludePatterns;
    
    if (isLocalRepo && hasSelectivePatterns) {
      writeLog(`Using selective file copying for local repository: ${repo.name}`);
      
      // Extract local path from file:// URL
      const localPath = repo.url.replace('file://', '').replace(/^\/*/, '');
      const normalizedPath = path.resolve(localPath);
      
      if (!fs.existsSync(normalizedPath)) {
        throw new Error(`Local repository path does not exist: ${normalizedPath}`);
      }
      
      // Ensure target directory exists
      if (!fs.existsSync(repo.targetPath)) {
        fs.mkdirSync(repo.targetPath, { recursive: true });
        writeLog(`Created directory: ${repo.targetPath}`);
      }
      
      // Clear target directory for fresh copy
      if (fs.existsSync(repo.targetPath)) {
        fs.rmSync(repo.targetPath, { recursive: true, force: true });
        fs.mkdirSync(repo.targetPath, { recursive: true });
      }
      
      // Copy selective files
      await copySelectiveFiles(
        normalizedPath,
        repo.targetPath,
        repo.includePatterns || [],
        repo.excludePatterns || []
      );
      
      writeLog(`Successfully copied selective content from ${repo.name}`, LOG_LEVELS.SUCCESS);
      return true;
    }
    
    // Standard git repository handling
    const targetDir = path.dirname(repo.targetPath);
    if (!fs.existsSync(targetDir)) {
      fs.mkdirSync(targetDir, { recursive: true });
      writeLog(`Created directory: ${targetDir}`);
    }
    
    if (isGitRepository(repo.targetPath)) {
      // Update existing repository
      writeLog(`Updating existing repository: ${repo.name}`);
      
      // Fetch latest changes
      executeGitCommand('git fetch origin', repo.targetPath);
      
      // Get current branch
      const currentBranch = executeGitCommand('git branch --show-current', repo.targetPath);
      
      // Switch to target branch if different
      if (currentBranch !== repo.branch) {
        executeGitCommand(`git checkout ${repo.branch}`, repo.targetPath);
      }
      
      // Pull latest changes
      executeGitCommand(`git pull origin ${repo.branch}`, repo.targetPath);
      
      writeLog(`Successfully updated ${repo.name}`, LOG_LEVELS.SUCCESS);
    } else {
      // Clone new repository
      writeLog(`Cloning repository: ${repo.name}`);
      
      // Remove target directory if it exists but is not a git repo
      if (fs.existsSync(repo.targetPath)) {
        fs.rmSync(repo.targetPath, { recursive: true, force: true });
      }
      
      // Clone repository
      executeGitCommand(`git clone -b ${repo.branch} ${repo.url} ${repo.targetPath}`);
      
      writeLog(`Successfully cloned ${repo.name}`, LOG_LEVELS.SUCCESS);
    }
    
    return true;
  } catch (error) {
    writeLog(`Error updating ${repo.name}: ${error.message}`, LOG_LEVELS.ERROR);
    return false;
  }
}

/**
 * Update .gitignore to exclude external repositories
 */
function updateGitignore() {
  const gitignorePath = '.gitignore';
  const externalIgnore = '\n# External repositories (auto-managed)\nexternal/\n';
  
  try {
    let gitignoreContent = '';
    
    if (fs.existsSync(gitignorePath)) {
      gitignoreContent = fs.readFileSync(gitignorePath, 'utf8');
    }
    
    if (!gitignoreContent.includes('external/')) {
      fs.appendFileSync(gitignorePath, externalIgnore);
      writeLog('Added external/ to .gitignore');
    }
  } catch (error) {
    writeLog(`Failed to update .gitignore: ${error.message}`, LOG_LEVELS.WARN);
  }
}

/**
 * Generate update report
 * @param {number} successCount - Number of successful updates
 * @param {number} totalCount - Total number of repositories
 */
function generateReport(successCount, totalCount) {
  writeLog('=== External Repository Update Report ===');
  writeLog(`Timestamp: ${new Date().toISOString()}`);
  writeLog(`Success Rate: ${successCount}/${totalCount} repositories updated`);
  
  // List external directories
  const externalDir = 'external';
  if (fs.existsSync(externalDir)) {
    writeLog('\nExternal repositories found:');
    
    const dirs = fs.readdirSync(externalDir, { withFileTypes: true })
      .filter(dirent => dirent.isDirectory())
      .map(dirent => dirent.name);
    
    dirs.forEach(dirName => {
      const repoPath = path.join(externalDir, dirName);
      if (isGitRepository(repoPath)) {
        try {
          const lastCommit = executeGitCommand('git log -1 --format="%h - %s (%cr)"', repoPath);
          const branch = executeGitCommand('git branch --show-current', repoPath);
          writeLog(`  📁 ${dirName} (branch: ${branch})`);
          writeLog(`     Latest: ${lastCommit}`);
        } catch (error) {
          writeLog(`  📁 ${dirName} (error reading git info)`, LOG_LEVELS.WARN);
        }
      }
    });
  } else {
    writeLog('\nNo external repositories directory found');
  }
  
  writeLog('=== End Report ===');
}

/**
 * Main execution function
 */
async function main() {
  try {
    writeLog('Starting external repository update process');
    
    // Load configuration
    const config = loadConfiguration();
    const enabledRepos = config.repositories.filter(repo => repo.enabled !== false);
    const settings = config.settings || {};
    
    writeLog(`Found ${enabledRepos.length} enabled repositories`);
    
    // Update repositories
    let successCount = 0;
    const totalCount = enabledRepos.length;
    
    for (const repo of enabledRepos) {
      const success = await updateExternalRepository(repo);
      if (success) {
        successCount++;
      }
    }
    
    // Update .gitignore
    updateGitignore();
    
    // Generate report
    generateReport(successCount, totalCount);
    
    // Exit with appropriate code
    if (successCount === totalCount) {
      writeLog('All repositories updated successfully', LOG_LEVELS.SUCCESS);
      process.exit(0);
    } else {
      writeLog(`${totalCount - successCount} repositories failed to update`, LOG_LEVELS.WARN);
      process.exit(1);
    }
    
  } catch (error) {
    writeLog(`External repository update failed: ${error.message}`, LOG_LEVELS.ERROR);
    process.exit(1);
  }
}

// Handle command line arguments
if (process.argv[1] === __filename) {
  // Parse command line arguments
  const args = process.argv.slice(2);
  const forceUpdate = args.includes('--force') || args.includes('-f');
  const verbose = args.includes('--verbose') || args.includes('-v');
  
  if (args.includes('--help') || args.includes('-h')) {
    console.log(`
External Repository Update Script

Usage: node update-external-repos.js [options]

Options:
  -f, --force     Force update even if no changes detected
  -v, --verbose   Enable verbose logging
  -h, --help      Show this help message

Examples:
  node update-external-repos.js
  node update-external-repos.js --force
  node update-external-repos.js --verbose
`);
    process.exit(0);
  }
  
  // Set verbose mode if requested
  if (verbose) {
    writeLog('Verbose mode enabled');
  }
  
  // Run main function
  (async () => {
    await main();
  })();
}

export {
  loadConfiguration,
  updateExternalRepository,
  writeLog,
  LOG_LEVELS
};