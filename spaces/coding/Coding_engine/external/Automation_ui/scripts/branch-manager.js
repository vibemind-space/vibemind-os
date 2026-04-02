#!/usr/bin/env node

/**
 * Branch Management Script for Multi-Repository Workflow
 * Part of autonomous programmer project - manages branch operations across repositories
 * Author: Autonomous Agent
 * Purpose: Handle branch switching and management for external repositories
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
 * @param {string} level - Log level
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
 * Load external repository configuration
 * @returns {Object} Configuration object
 */
function loadConfiguration() {
  try {
    if (!fs.existsSync(CONFIG_PATH)) {
      throw new Error(`Configuration file not found: ${CONFIG_PATH}`);
    }
    
    const configContent = fs.readFileSync(CONFIG_PATH, 'utf8');
    const config = JSON.parse(configContent);
    
    if (!config.repositories || !Array.isArray(config.repositories)) {
      throw new Error('Invalid configuration: repositories array is required');
    }
    
    return config;
  } catch (error) {
    writeLog(`Failed to load configuration: ${error.message}`, LOG_LEVELS.ERROR);
    throw error;
  }
}

/**
 * Update repository branch configuration
 * @param {string} repoName - Repository name
 * @param {string} newBranch - New branch name
 */
function updateRepositoryBranch(repoName, newBranch) {
  try {
    const config = loadConfiguration();
    const repo = config.repositories.find(r => r.name === repoName);
    
    if (!repo) {
      throw new Error(`Repository '${repoName}' not found in configuration`);
    }
    
    const oldBranch = repo.branch;
    repo.branch = newBranch;
    
    // Save updated configuration
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2));
    
    writeLog(`Updated ${repoName} branch: ${oldBranch} -> ${newBranch}`, LOG_LEVELS.SUCCESS);
    
    // If repository exists locally, switch branch
    if (fs.existsSync(repo.targetPath) && fs.existsSync(path.join(repo.targetPath, '.git'))) {
      switchLocalBranch(repo.targetPath, newBranch);
    }
    
  } catch (error) {
    writeLog(`Failed to update repository branch: ${error.message}`, LOG_LEVELS.ERROR);
    throw error;
  }
}

/**
 * Switch local repository branch
 * @param {string} repoPath - Local repository path
 * @param {string} branchName - Branch name to switch to
 */
function switchLocalBranch(repoPath, branchName) {
  try {
    writeLog(`Switching to branch '${branchName}' in ${repoPath}`);
    
    // Fetch latest changes
    executeGitCommand('git fetch origin', repoPath);
    
    // Check if branch exists locally
    try {
      executeGitCommand(`git show-ref --verify --quiet refs/heads/${branchName}`, repoPath);
      // Branch exists locally, switch to it
      executeGitCommand(`git checkout ${branchName}`, repoPath);
    } catch {
      // Branch doesn't exist locally, create and track remote branch
      try {
        executeGitCommand(`git checkout -b ${branchName} origin/${branchName}`, repoPath);
      } catch {
        // Remote branch doesn't exist, create new branch
        executeGitCommand(`git checkout -b ${branchName}`, repoPath);
        writeLog(`Created new branch '${branchName}'`, LOG_LEVELS.WARN);
      }
    }
    
    // Pull latest changes
    executeGitCommand(`git pull origin ${branchName}`, repoPath);
    
    writeLog(`Successfully switched to branch '${branchName}'`, LOG_LEVELS.SUCCESS);
    
  } catch (error) {
    writeLog(`Failed to switch branch: ${error.message}`, LOG_LEVELS.ERROR);
    throw error;
  }
}

/**
 * List all repositories and their current branches
 */
function listRepositoryBranches() {
  try {
    const config = loadConfiguration();
    
    writeLog('=== Repository Branch Status ===');
    
    config.repositories.forEach(repo => {
      writeLog(`\n📁 ${repo.name}`);
      writeLog(`   Team: ${repo.team}`);
      writeLog(`   Configured Branch: ${repo.branch}`);
      
      if (fs.existsSync(repo.targetPath) && fs.existsSync(path.join(repo.targetPath, '.git'))) {
        try {
          const currentBranch = executeGitCommand('git branch --show-current', repo.targetPath);
          const status = currentBranch === repo.branch ? '✅' : '⚠️';
          writeLog(`   Current Branch: ${currentBranch} ${status}`);
          
          // Show available branches
          const branches = executeGitCommand('git branch -r', repo.targetPath)
            .split('\n')
            .map(b => b.trim().replace('origin/', ''))
            .filter(b => b && !b.includes('HEAD'))
            .slice(0, 5); // Show first 5 branches
          
          writeLog(`   Available Branches: ${branches.join(', ')}`);
        } catch (error) {
          writeLog(`   Status: Error reading git info`, LOG_LEVELS.WARN);
        }
      } else {
        writeLog(`   Status: Not cloned locally`);
      }
    });
    
    writeLog('\n=== End Status ===');
    
  } catch (error) {
    writeLog(`Failed to list repository branches: ${error.message}`, LOG_LEVELS.ERROR);
    throw error;
  }
}

/**
 * Create a new working branch for development
 * @param {string} repoName - Repository name
 * @param {string} branchName - New branch name
 * @param {string} baseBranch - Base branch to create from
 */
function createWorkingBranch(repoName, branchName, baseBranch = 'main') {
  try {
    const config = loadConfiguration();
    const repo = config.repositories.find(r => r.name === repoName);
    
    if (!repo) {
      throw new Error(`Repository '${repoName}' not found in configuration`);
    }
    
    if (!fs.existsSync(repo.targetPath) || !fs.existsSync(path.join(repo.targetPath, '.git'))) {
      throw new Error(`Repository not found locally: ${repo.targetPath}`);
    }
    
    writeLog(`Creating working branch '${branchName}' from '${baseBranch}' in ${repoName}`);
    
    // Fetch latest changes
    executeGitCommand('git fetch origin', repo.targetPath);
    
    // Switch to base branch and pull
    executeGitCommand(`git checkout ${baseBranch}`, repo.targetPath);
    executeGitCommand(`git pull origin ${baseBranch}`, repo.targetPath);
    
    // Create new branch
    executeGitCommand(`git checkout -b ${branchName}`, repo.targetPath);
    
    writeLog(`Successfully created working branch '${branchName}'`, LOG_LEVELS.SUCCESS);
    
  } catch (error) {
    writeLog(`Failed to create working branch: ${error.message}`, LOG_LEVELS.ERROR);
    throw error;
  }
}

/**
 * Main execution function
 */
function main() {
  const args = process.argv.slice(2);
  
  if (args.includes('--help') || args.includes('-h') || args.length === 0) {
    console.log(`
Branch Management Script for Multi-Repository Workflow

Usage: node branch-manager.js <command> [options]

Commands:
  list                           List all repositories and their branch status
  switch <repo> <branch>         Switch repository to specified branch
  create <repo> <branch> [base]  Create new working branch from base branch
  update <repo> <branch>         Update repository configuration to use new branch

Examples:
  node branch-manager.js list
  node branch-manager.js switch autogen-event-agents feature/api-docs
  node branch-manager.js create autogen-event-agents feature/new-events main
  node branch-manager.js update autogen-event-agents develop

Options:
  -h, --help                     Show this help message
`);
    process.exit(0);
  }
  
  const command = args[0];
  
  try {
    switch (command) {
      case 'list':
        listRepositoryBranches();
        break;
        
      case 'switch':
        if (args.length < 3) {
          throw new Error('Usage: switch <repo> <branch>');
        }
        const repoName = args[1];
        const branchName = args[2];
        updateRepositoryBranch(repoName, branchName);
        break;
        
      case 'create':
        if (args.length < 3) {
          throw new Error('Usage: create <repo> <branch> [base]');
        }
        const createRepo = args[1];
        const createBranch = args[2];
        const baseBranch = args[3] || 'main';
        createWorkingBranch(createRepo, createBranch, baseBranch);
        break;
        
      case 'update':
        if (args.length < 3) {
          throw new Error('Usage: update <repo> <branch>');
        }
        const updateRepo = args[1];
        const updateBranch = args[2];
        updateRepositoryBranch(updateRepo, updateBranch);
        break;
        
      default:
        throw new Error(`Unknown command: ${command}`);
    }
    
  } catch (error) {
    writeLog(`Branch management failed: ${error.message}`, LOG_LEVELS.ERROR);
    process.exit(1);
  }
}

// Run main function if script is executed directly
if (process.argv[1] === __filename) {
  main();
}

export {
  updateRepositoryBranch,
  switchLocalBranch,
  listRepositoryBranches,
  createWorkingBranch,
  writeLog,
  LOG_LEVELS
};