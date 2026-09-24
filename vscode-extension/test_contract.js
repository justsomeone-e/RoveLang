'use strict';

const assert = require('assert');
const fs = require('fs');
const Module = require('module');
const path = require('path');

const events = [];
let clientOptions;
let serverOptions;
let completionItemProvider;
let completionSelector;
let completionTriggers;
const registeredCommands = new Map();
const executedTasks = [];
const openedExternalUrls = [];
const persistedState = new Map();

class MockLanguageClient {
    constructor(id, name, server, client) {
        assert.strictEqual(id, 'roveLanguageServer');
        assert.strictEqual(name, 'Rove Language Server');
        serverOptions = server;
        clientOptions = client;
    }

    async start() {
        events.push('start');
    }

    async stop() {
        events.push('stop');
    }
}

const vscodeMock = {
    env: {
        async openExternal(uri) {
            openedExternalUrls.push(uri.toString());
            return true;
        }
    },
    Uri: {
        parse(value) {
            return { toString: () => value };
        }
    },
    workspace: {
        getConfiguration(section) {
            assert.ok(section === 'rove.server' || section === 'rove.run');
            return { get: (_key, fallback) => fallback };
        },
        getWorkspaceFolder() { return undefined; }
    },
    window: {
        activeTextEditor: {
            document: {
                languageId: 'rovelang',
                isUntitled: false,
                isDirty: true,
                uri: { fsPath: 'C:\\project\\main.rove', path: '/C:/project/main.rove' },
                getText: () => '#target cpp\nprint("hello")',
                save: async () => true
            }
        },
        async showWarningMessage() { return undefined; },
        async showInformationMessage() { return 'Continue'; },
        createStatusBarItem() {
            return { show() {}, dispose() {} };
        }
    },
    commands: {
        registerCommand(id, handler) {
            registeredCommands.set(id, handler);
            return { dispose() {} };
        }
    },
    tasks: {
        async executeTask(task) {
            executedTasks.push(task);
            return task;
        }
    },
    languages: {
        registerCompletionItemProvider(selector, provider, ...triggers) {
            events.push('completion-provider');
            completionSelector = selector;
            completionTriggers = triggers;
            completionItemProvider = provider;
            return { dispose() {} };
        }
    },
    CompletionItemKind: {
        Keyword: 14,
        Snippet: 15,
        Function: 3,
        TypeParameter: 25
    },
    CompletionItem: class {
        constructor(label, kind) {
            this.label = label;
            this.kind = kind;
        }
    },
    SnippetString: class {
        constructor(value) { this.value = value; }
    },
    MarkdownString: class {
        constructor(value) { this.value = value; }
    },
    Range: class {},
    Position: class {},
    ShellExecution: class {
        constructor(command, args) {
            this.command = command;
            this.args = args;
        }
    },
    Task: class {
        constructor(definition, scope, name, source, execution, problemMatchers) {
            Object.assign(this, { definition, scope, name, source, execution, problemMatchers });
        }
    },
    TaskScope: { Workspace: 1 },
    TaskRevealKind: { Always: 1 },
    TaskPanelKind: { Shared: 1 },
    StatusBarAlignment: { Left: 1 }
};

const originalLoad = Module._load;
Module._load = function(request, parent, isMain) {
    if (request === 'vscode') {
        return vscodeMock;
    }
    if (request === 'vscode-languageclient/node') {
        return { LanguageClient: MockLanguageClient };
    }
    return originalLoad.call(this, request, parent, isMain);
};

async function main() {
    const manifest = require(path.join(__dirname, 'package.json'));
    assert.strictEqual(manifest.displayName, 'Rove Language Toolchain');
    assert.strictEqual(manifest.icon, 'images/rove-icon.png');
    assert.strictEqual(manifest.homepage, 'https://github.com/justsomeone-e/RoveLang#readme');
    assert.strictEqual(manifest.bugs.url, 'https://github.com/justsomeone-e/RoveLang/issues');
    assert.deepStrictEqual(manifest.galleryBanner, { color: '#171A35', theme: 'dark' });
    assert.ok(fs.existsSync(path.join(__dirname, manifest.icon)));
    const language = manifest.contributes.languages.find(item => item.id === 'rovelang');
    assert.deepStrictEqual(language.icon, {
        light: './images/rove-file-icon.png',
        dark: './images/rove-file-icon.png'
    });
    assert.ok(fs.existsSync(path.join(__dirname, language.icon.light)));
    const grammarPath = path.join(__dirname, manifest.contributes.grammars[0].path);
    const grammar = JSON.parse(fs.readFileSync(grammarPath, 'utf8'));
    const nativeBlocks = new Map(
        grammar.patterns
            .filter(item => item.name && item.name.startsWith('meta.preprocessor.native.') && item.name.endsWith('.block.rove'))
            .map(item => [item.name, item])
    );
    for (const [name, embeddedScope] of [
        ['meta.preprocessor.native.cpp.block.rove', 'source.cpp'],
        ['meta.preprocessor.native.js.block.rove', 'source.js'],
        ['meta.preprocessor.native.rust.block.rove', 'source.rust']
    ]) {
        const nativeBlock = nativeBlocks.get(name);
        assert.ok(nativeBlock, `missing ${name} syntax grammar`);
        assert.ok(nativeBlock.patterns.some(item => item.include === embeddedScope));
    }
    const commandIds = new Set(manifest.contributes.commands.map(item => item.command));
    for (const id of [
        'rove.runCurrentFile',
        'rove.buildCurrentFile',
        'rove.checkCurrentFile',
        'rove.toolchainDoctor',
        'rove.openRepository',
        'rove.openDocumentation',
        'rove.openReleases',
        'rove.openRoadmap',
        'rove.reportIssue'
    ]) {
        assert.ok(commandIds.has(id), `missing command contribution: ${id}`);
    }

    const {
        createServerOptions,
        resolveRoveCommand
    } = require(path.join(__dirname, 'server_options.js'));
    const canonicalWindowsCli = 'C:\\Users\\Rove\\.rove\\bin\\rove.cmd';
    assert.strictEqual(
        resolveRoveCommand(
            'rove',
            'win32',
            { USERPROFILE: 'C:\\Users\\Rove' },
            candidate => candidate === canonicalWindowsCli
        ),
        canonicalWindowsCli
    );
    assert.strictEqual(
        resolveRoveCommand('rove', 'linux', { HOME: '/home/rove' }, () => false),
        'rove'
    );
    if (process.platform === 'win32') {
        const customShim = createServerOptions(
            'C:\\Program Files\\Rove\\rove.cmd'
        );
        assert.deepStrictEqual(customShim.args, [
            '/d', '/s', '/v:off', '/c',
            '"C:\\Program Files\\Rove\\rove.cmd" lsp'
        ]);
        assert.throws(
            () => createServerOptions('%TEMP%\\rove.cmd'),
            /unsafe/
        );
        assert.throws(
            () => createServerOptions('C:\\Rove & tools\\rove.cmd'),
            /unsafe/
        );
    }
    assert.deepStrictEqual(
        createServerOptions('/opt/rove/bin/rove', 'linux', {}),
        {
            command: '/opt/rove/bin/rove',
            args: ['lsp'],
            options: { windowsHide: true }
        }
    );

    const extension = require(path.join(__dirname, 'extension.js'));
    const context = {
        subscriptions: [],
        globalState: {
            get: (key, fallback) => persistedState.has(key) ? persistedState.get(key) : fallback,
            update: async (key, value) => persistedState.set(key, value)
        }
    };
    await extension.activate(context);

    const resolvedDefaultCli = resolveRoveCommand('rove');
    if (process.platform === 'win32') {
        const windowsDefaultCli = resolvedDefaultCli === 'rove'
            ? 'rove.cmd'
            : resolvedDefaultCli;
        assert.strictEqual(serverOptions.command, process.env.ComSpec || 'cmd.exe');
        assert.deepStrictEqual(serverOptions.args, [
            '/d', '/s', '/v:off', '/c', `"${windowsDefaultCli}" lsp`
        ]);
        assert.deepStrictEqual(serverOptions.options, {
            windowsHide: true,
            windowsVerbatimArguments: true
        });
    } else {
        assert.strictEqual(serverOptions.command, resolvedDefaultCli);
        assert.deepStrictEqual(serverOptions.args, ['lsp']);
        assert.deepStrictEqual(serverOptions.options, { windowsHide: true });
    }
    assert.deepStrictEqual(clientOptions.documentSelector, [
        { scheme: 'file', language: 'rovelang' },
        { scheme: 'untitled', language: 'rovelang' }
    ]);
    assert.deepStrictEqual(events, ['start', 'completion-provider']);
    assert.strictEqual(completionSelector, 'rovelang');
    for (const trigger of ['a', 'z', '_']) {
        assert.ok(completionTriggers.includes(trigger), `missing completion trigger: ${trigger}`);
    }
    assert.strictEqual(context.subscriptions.length, 12);
    assert.strictEqual(registeredCommands.size, 9);

    await registeredCommands.get('rove.runCurrentFile')();
    assert.strictEqual(executedTasks.length, 1);
    assert.strictEqual(executedTasks[0].execution.command, resolvedDefaultCli);
    assert.deepStrictEqual(
        executedTasks[0].execution.args,
        ['run', 'C:\\project\\main.rove']
    );
    assert.strictEqual(executedTasks[0].presentationOptions.reveal, 1);
    assert.strictEqual(executedTasks[0].presentationOptions.panel, 1);

    for (const commandId of [
        'rove.openRepository',
        'rove.openDocumentation',
        'rove.openReleases',
        'rove.openRoadmap',
        'rove.reportIssue'
    ]) {
        await registeredCommands.get(commandId)();
    }
    assert.deepStrictEqual(openedExternalUrls, [
        'https://github.com/justsomeone-e/RoveLang',
        'https://github.com/justsomeone-e/RoveLang#readme',
        'https://github.com/justsomeone-e/RoveLang/releases',
        'https://github.com/justsomeone-e/RoveLang/blob/main/docs/internals/ROADMAP_AND_BACKEND_GATES.md',
        'https://github.com/justsomeone-e/RoveLang/issues/new'
    ]);

    const languageSurface = require(path.join(__dirname, 'language-surface.json'));
    const snippets = require(path.join(__dirname, 'snippets', 'rove.snippets.json'));
    const targetSnippet = snippets['Target Directive'].body.join('\n');
    for (const target of languageSurface.targets) {
        assert.ok(targetSnippet.includes(target.name), `target snippet missing ${target.name}`);
    }
    const targetItems = completionItemProvider.provideCompletionItems(
        {
            lineAt: () => ({ text: '#target' }),
            getText: () => '#target'
        },
        { line: 0, character: 7 },
        undefined,
        undefined
    );
    assert.deepStrictEqual(
        targetItems.map(item => item.label),
        languageSurface.targets.map(target => target.name)
    );
    const completionSource = 'import "std/fs"\nfn local_helper(value: int) -> int {\n    let local_value = value\n}\na';
    const completionItems = completionItemProvider.provideCompletionItems(
        {
            lineAt: () => ({ text: 'a' }),
            getText: () => completionSource
        },
        { line: 4, character: 1 },
        undefined,
        undefined
    );
    const labels = new Set(completionItems.map(item => item.label));
    for (const keyword of languageSurface.stableKeywords) {
        assert.ok(labels.has(keyword), `missing stable Rove completion: ${keyword}`);
    }
    for (const keyword of languageSurface.reservedKeywords) {
        assert.ok(!labels.has(keyword), `reserved keyword must not be advertised: ${keyword}`);
    }
    assert.ok(labels.has('continue'));
    assert.ok(labels.has('async'));
    for (const canonicalLabel of [
        'append_string',
        'fnv1a_64_hex',
        'cpp',
        'llvm',
        'args',
        'local_helper',
        'local_value'
    ]) {
        assert.ok(labels.has(canonicalLabel), `missing canonical completion: ${canonicalLabel}`);
    }
    assert.ok(!labels.has('poke'), 'extension must not advertise a nonexistent core builtin');
    assert.ok(!labels.has('val'));

    await extension.deactivate();
    assert.deepStrictEqual(events, ['start', 'completion-provider', 'stop']);
    process.stdout.write('[PASS] VS Code extension launches rove lsp through LanguageClient\n');
}

main().finally(() => {
    Module._load = originalLoad;
}).catch(error => {
    console.error(error);
    process.exitCode = 1;
});
