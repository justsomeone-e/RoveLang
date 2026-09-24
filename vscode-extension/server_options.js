'use strict';

const fs = require('fs');
const path = require('path');

function resolveRoveCommand(
    configuredPath,
    platform = process.platform,
    env = process.env,
    existsSync = fs.existsSync
) {
    const command = String(configuredPath || '').trim();
    if (!command || command !== 'rove') return command;

    const home = env.USERPROFILE || env.HOME;
    if (!home) return command;
    const executable = platform === 'win32' ? 'rove.cmd' : 'rove';
    const pathApi = platform === 'win32' ? path.win32 : path.posix;
    const canonical = pathApi.join(home, '.rove', 'bin', executable);
    return existsSync(canonical) ? canonical : command;
}

function createServerOptions(configuredPath, platform = process.platform, env = process.env) {
    const command = resolveRoveCommand(configuredPath, platform, env);
    if (!command) {
        throw new Error('rove.server.path must name an executable or command shim');
    }

    if (platform !== 'win32') {
        return {
            command,
            args: ['lsp'],
            options: { windowsHide: true }
        };
    }

    const windowsCommand = command === 'rove' ? 'rove.cmd' : command;
    if (!/\.(?:cmd|bat)$/i.test(windowsCommand)) {
        return {
            command: windowsCommand,
            args: ['lsp'],
            options: { windowsHide: true }
        };
    }
    if (/[\0\r\n"%&|<>^()]/.test(windowsCommand)) {
        throw new Error('rove.server.path contains characters unsafe for a Windows command shim');
    }

    // .cmd/.bat files are scripts, not PE executables. Launch cmd.exe
    // explicitly instead of child_process' shell mode; this avoids spawn
    // EINVAL and keeps argument handling deterministic on current Node.js.
    return {
        command: env.ComSpec || 'cmd.exe',
        args: ['/d', '/s', '/v:off', '/c', `"${windowsCommand}" lsp`],
        options: { windowsHide: true, windowsVerbatimArguments: true }
    };
}

module.exports = { createServerOptions, resolveRoveCommand };
