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
        assert.strictEqual(id, 'nyxLanguageServer');
        assert.strictEqual(name, 'Nyx Language Server');
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
            assert.ok(section === 'nyx.server' || section === 'nyx.run');
            return { get: (_key, fallback) => fallback };
        },
        getWorkspaceFolder() { return undefined; }
    },
    window: {
        activeTextEditor: {
            document: {
                languageId: 'nyxlang',
                isUntitled: false,
                isDirty: true,
                uri: { fsPath: 'C:\\project\\main.nyx', path: '/C:/project/main.nyx' },
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
    assert.strictEqual(manifest.displayName, 'Nyx Language Toolchain');
    assert.strictEqual(manifest.icon, 'images/nyx-icon.png');
    assert.strictEqual(manifest.homepage, 'https://github.com/justsomeone-e/nyx#readme');
    assert.strictEqual(manifest.bugs.url, 'https://github.com/justsomeone-e/nyx/issues');
    assert.deepStrictEqual(manifest.galleryBanner, { color: '#171A35', theme: 'dark' });
    assert.ok(fs.existsSync(path.join(__dirname, manifest.icon)));
    const language = manifest.contributes.languages.find(item => item.id === 'nyxlang');
    assert.deepStrictEqual(language.icon, {
        light: './images/nyx-file-icon.png',
        dark: './images/nyx-file-icon.png'
    });
    assert.ok(fs.existsSync(path.join(__dirname, language.icon.light)));
    const grammarPath = path.join(__dirname, manifest.contributes.grammars[0].path);
    const grammar = JSON.parse(fs.readFileSync(grammarPath, 'utf8'));
    const nativeBlocks = new Map(
        grammar.patterns
            .filter(item => item.name && item.name.startsWith('meta.preprocessor.native.') && item.name.endsWith('.block.nyx'))
            .map(item => [item.name, item])
    );
    for (const [name, embeddedScope] of [
        ['meta.preprocessor.native.cpp.block.nyx', 'source.cpp'],
        ['meta.preprocessor.native.js.block.nyx', 'source.js'],
        ['meta.preprocessor.native.rust.block.nyx', 'source.rust']
    ]) {
        const nativeBlock = nativeBlocks.get(name);
        assert.ok(nativeBlock, `missing ${name} syntax grammar`);
        assert.ok(nativeBlock.patterns.some(item => item.include === embeddedScope));
    }
    const commandIds = new Set(manifest.contributes.commands.map(item => item.command));
    for (const id of [
        'nyx.runCurrentFile',
        'nyx.buildCurrentFile',
        'nyx.checkCurrentFile',
        'nyx.toolchainDoctor',
        'nyx.openRepository',
        'nyx.openDocumentation',
        'nyx.openReleases',
        'nyx.openRoadmap',
        'nyx.reportIssue'
    ]) {
        assert.ok(commandIds.has(id), `missing command contribution: ${id}`);
    }

    const {
        createServerOptions,
        resolveNyxCommand
    } = require(path.join(__dirname, 'server_options.js'));
    const canonicalWindowsCli = 'C:\\Users\\Nyx\\.nyx\\bin\\nyx.cmd';
    assert.strictEqual(
        resolveNyxCommand(
            'nyx',
            'win32',
            { USERPROFILE: 'C:\\Users\\Nyx' },
            candidate => candidate === canonicalWindowsCli
        ),
        canonicalWindowsCli
    );
    assert.strictEqual(
        resolveNyxCommand('nyx', 'linux', { HOME: '/home/nyx' }, () => false),
        'nyx'
    );
    if (process.platform === 'win32') {
        const customShim = createServerOptions(
            'C:\\Program Files\\Nyx\\nyx.cmd'
        );
        assert.deepStrictEqual(customShim.args, [
            '/d', '/s', '/v:off', '/c',
            '"C:\\Program Files\\Nyx\\nyx.cmd" lsp'
        ]);
        assert.throws(
            () => createServerOptions('%TEMP%\\nyx.cmd'),
            /unsafe/
        );
        assert.throws(
            () => createServerOptions('C:\\Nyx & tools\\nyx.cmd'),
            /unsafe/
        );
    }
    assert.deepStrictEqual(
        createServerOptions('/opt/nyx/bin/nyx', 'linux', {}),
        {
            command: '/opt/nyx/bin/nyx',
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

    const resolvedDefaultCli = resolveNyxCommand('nyx');
    if (process.platform === 'win32') {
        const windowsDefaultCli = resolvedDefaultCli === 'nyx'
            ? 'nyx.cmd'
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
        { scheme: 'file', language: 'nyxlang' },
        { scheme: 'untitled', language: 'nyxlang' }
    ]);
    assert.deepStrictEqual(events, ['start', 'completion-provider']);
    assert.strictEqual(completionSelector, 'nyxlang');
    for (const trigger of ['a', 'z', '_']) {
        assert.ok(completionTriggers.includes(trigger), `missing completion trigger: ${trigger}`);
    }
    assert.strictEqual(context.subscriptions.length, 12);
    assert.strictEqual(registeredCommands.size, 9);

    await registeredCommands.get('nyx.runCurrentFile')();
    assert.strictEqual(executedTasks.length, 1);
    assert.strictEqual(executedTasks[0].execution.command, resolvedDefaultCli);
    assert.deepStrictEqual(
        executedTasks[0].execution.args,
        ['run', 'C:\\project\\main.nyx']
    );
    assert.strictEqual(executedTasks[0].presentationOptions.reveal, 1);
    assert.strictEqual(executedTasks[0].presentationOptions.panel, 1);

    for (const commandId of [
        'nyx.openRepository',
        'nyx.openDocumentation',
        'nyx.openReleases',
        'nyx.openRoadmap',
        'nyx.reportIssue'
    ]) {
        await registeredCommands.get(commandId)();
    }
    assert.deepStrictEqual(openedExternalUrls, [
        'https://github.com/justsomeone-e/nyx',
        'https://github.com/justsomeone-e/nyx#readme',
        'https://github.com/justsomeone-e/nyx/releases',
        'https://github.com/justsomeone-e/nyx/blob/main/docs/internals/ROADMAP_AND_BACKEND_GATES.md',
        'https://github.com/justsomeone-e/nyx/issues/new'
    ]);

    const languageSurface = require(path.join(__dirname, 'language-surface.json'));
    const snippets = require(path.join(__dirname, 'snippets', 'nyx.snippets.json'));
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
        assert.ok(labels.has(keyword), `missing stable Nyx completion: ${keyword}`);
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
    process.stdout.write('[PASS] VS Code extension launches nyx lsp through LanguageClient\n');
}

main().finally(() => {
    Module._load = originalLoad;
}).catch(error => {
    console.error(error);
    process.exitCode = 1;
});
