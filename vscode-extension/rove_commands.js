'use strict';

const { resolveRoveCommand } = require('./server_options');

const NATIVE_REQUIREMENT =
    'Rove cpp builds require Clang++, GCC/G++, or MSVC cl with C++20 support. ' +
    'Put the compiler on PATH or set ROVE_CXX; run “Rove: Toolchain Doctor” to verify it.';

const PROJECT_LINKS = Object.freeze({
    repository: 'https://github.com/justsomeone-e/RoveLang',
    documentation: 'https://github.com/justsomeone-e/RoveLang#readme',
    releases: 'https://github.com/justsomeone-e/RoveLang/releases',
    roadmap: 'https://github.com/justsomeone-e/RoveLang/blob/main/docs/internals/ROADMAP_AND_BACKEND_GATES.md',
    issues: 'https://github.com/justsomeone-e/RoveLang/issues/new'
});

const LINK_COMMANDS = Object.freeze([
    ['rove.openRepository', 'GitHub repository', PROJECT_LINKS.repository],
    ['rove.openDocumentation', 'documentation', PROJECT_LINKS.documentation],
    ['rove.openReleases', 'release history', PROJECT_LINKS.releases],
    ['rove.openRoadmap', 'compiler roadmap', PROJECT_LINKS.roadmap],
    ['rove.reportIssue', 'issue reporter', PROJECT_LINKS.issues]
]);

function sourceTarget(document) {
    const match = document.getText().match(/^\s*#target\s+([A-Za-z0-9_]+)/m);
    return match ? match[1].toLowerCase() : 'cpp';
}

async function requireRoveDocument(vscode) {
    const editor = vscode.window.activeTextEditor;
    if (!editor || editor.document.languageId !== 'rovelang') {
        await vscode.window.showWarningMessage('Open a .rove file before running a Rove command.');
        return undefined;
    }
    if (editor.document.isUntitled || !editor.document.uri.fsPath) {
        await vscode.window.showWarningMessage('Save the Rove file before running it.');
        return undefined;
    }
    if (editor.document.isDirty && !(await editor.document.save())) {
        return undefined;
    }
    return editor.document;
}

function taskScope(vscode, document) {
    if (document) {
        const folder = vscode.workspace.getWorkspaceFolder(document.uri);
        if (folder) return folder;
    }
    if (vscode.workspace.workspaceFolders && vscode.workspace.workspaceFolders.length > 0) {
        return vscode.workspace.workspaceFolders[0];
    }
    return vscode.TaskScope.Global;
}

async function executeTask(vscode, action, document, target) {
    const configuredCli = vscode.workspace.getConfiguration('rove.server').get('path', 'rove');
    const cli = resolveRoveCommand(configuredCli);
    const args = [action];
    if (document) args.push(document.uri.fsPath);
    if (target && target !== 'source' && (action === 'run' || action === 'build')) {
        args.push('--target', target);
    }

    const label = action === 'doctor'
        ? 'Rove: Toolchain Doctor'
        : `Rove: ${action[0].toUpperCase()}${action.slice(1)} ${document.uri.path.split('/').pop()}`;
    const task = new vscode.Task(
        { type: 'rove', action },
        taskScope(vscode, document),
        label,
        'rove',
        new vscode.ShellExecution(cli, args),
        []
    );
    if (action === 'build') {
        task.group = vscode.TaskGroup.Build;
    }
    task.presentationOptions = {
        reveal: vscode.TaskRevealKind.Always,
        panel: vscode.TaskPanelKind.Shared,
        clear: false,
        focus: true,
        showReuseMessage: false
    };
    return vscode.tasks.executeTask(task);
}

async function maybeExplainNativeRequirement(vscode, context, action, document, configuredTarget) {
    if (action !== 'run' && action !== 'build') return true;
    const target = configuredTarget === 'source' ? sourceTarget(document) : configuredTarget;
    if (target !== 'cpp' && target !== 'cpp' && target !== 'native') return true;
    const key = 'rove.cppRequirementAcknowledged';
    if (context.globalState.get(key, false)) return true;

    const choice = await vscode.window.showInformationMessage(
        NATIVE_REQUIREMENT,
        'Continue',
        'Run Toolchain Doctor'
    );
    await context.globalState.update(key, true);
    if (choice === 'Run Toolchain Doctor') {
        await executeTask(vscode, 'doctor');
        return false;
    }
    return true;
}

async function openProjectLink(vscode, label, url) {
    const opened = await vscode.env.openExternal(vscode.Uri.parse(url));
    if (!opened) {
        await vscode.window.showWarningMessage(`Could not open the Rove ${label}: ${url}`);
    }
}

function registerRoveCommands(vscode, context) {
    const registrations = [];
    for (const [commandId, action] of [
        ['rove.runCurrentFile', 'run'],
        ['rove.buildCurrentFile', 'build'],
        ['rove.checkCurrentFile', 'check']
    ]) {
        registrations.push(vscode.commands.registerCommand(commandId, async () => {
            const document = await requireRoveDocument(vscode);
            if (!document) return;
            const configuredTarget = vscode.workspace
                .getConfiguration('rove.run')
                .get('target', 'source');
            if (!(await maybeExplainNativeRequirement(
                vscode, context, action, document, configuredTarget
            ))) return;
            await executeTask(vscode, action, document, configuredTarget);
        }));
    }
    registrations.push(vscode.commands.registerCommand('rove.toolchainDoctor', async () => {
        await executeTask(vscode, 'doctor');
    }));
    for (const [commandId, label, url] of LINK_COMMANDS) {
        registrations.push(vscode.commands.registerCommand(commandId, async () => {
            await openProjectLink(vscode, label, url);
        }));
    }

    const runButton = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 100);
    runButton.name = 'Run Rove File';
    runButton.text = '$(play) Rove';
    runButton.tooltip = 'Run the active Rove file in the integrated terminal';
    runButton.command = 'rove.runCurrentFile';
    runButton.show();
    registrations.push(runButton);

    context.subscriptions.push(...registrations);
    return registrations;
}

module.exports = {
    LINK_COMMANDS,
    NATIVE_REQUIREMENT,
    PROJECT_LINKS,
    executeTask,
    openProjectLink,
    registerRoveCommands,
    sourceTarget
};
