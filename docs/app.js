// ==========================================================================
// Tour of Nyx & WebAssembly Studio Engine
// Client-side execution, interactive 81-step curriculum, and free playground
// ==========================================================================

(function () {
  'use strict';

  const { evaluateNyx } = NyxPreview;

  const CACHE_VERSION = 'v4_clean_2';

  // --- State ---
  const state = {
    mode: 'tour', // 'tour' | 'playground'
    currentExerciseIndex: 0,
    playgroundTemplateIndex: 0,
    activePanel: 'output',
    exercises: window.NYX_TOUR_DATA || [],
    completed: JSON.parse(localStorage.getItem('nyx_tour_completed') || '{}'),
    userCodeCache: JSON.parse(localStorage.getItem('nyx_tour_code_cache') || '{}'),
    editor: null
  };

  // --- DOM Elements ---
  const el = {
    leftPane: document.getElementById('leftPane'),
    curriculumDrawer: document.getElementById('curriculumDrawer'),
    btnToggleDrawer: document.getElementById('btnToggleDrawer'),
    btnCloseDrawer: document.getElementById('btnCloseDrawer'),
    exerciseTree: document.getElementById('exerciseTree'),
    searchExercises: document.getElementById('searchExercises'),
    badgeTopic: document.getElementById('badgeTopic'),
    badgeStatus: document.getElementById('badgeStatus'),
    exerciseTitle: document.getElementById('exerciseTitle'),
    exerciseDesc: document.getElementById('exerciseDesc'),
    expectedOutputBox: document.getElementById('expectedOutputBox'),
    hintBox: document.getElementById('hintBox'),
    hintBtnText: document.getElementById('hintBtnText'),
    btnToggleHint: document.getElementById('btnToggleHint'),
    btnShowSolution: document.getElementById('btnShowSolution'),
    btnPrevExercise: document.getElementById('btnPrevExercise'),
    btnNextExercise: document.getElementById('btnNextExercise'),
    lessonCounter: document.getElementById('lessonCounter'),
    editorFilename: document.getElementById('editorFilename'),
    btnRun: document.getElementById('btnRun'),
    btnInspect: document.getElementById('btnInspect'),
    btnResetCode: document.getElementById('btnResetCode'),
    targetSelect: document.getElementById('targetSelect'),
    templateSelect: document.getElementById('templateSelect'),
    paneResizer: document.getElementById('paneResizer'),
    terminalSection: document.getElementById('terminalSection'),
    execStatusBadge: document.getElementById('execStatusBadge'),
    btnClearTerminal: document.getElementById('btnClearTerminal'),
    terminalView: document.getElementById('terminalView'),
    inspectionView: document.getElementById('inspectionView'),
    buildView: document.getElementById('buildView'),
    sourceStats: document.getElementById('sourceStats'),
    pipelineTarget: document.getElementById('pipelineTarget'),
    inspectionStatus: document.getElementById('inspectionStatus'),
    inspectionNote: document.getElementById('inspectionNote'),
    buildTargetStatus: document.getElementById('buildTargetStatus'),
    buildNote: document.getElementById('buildNote'),
    buildCommand: document.getElementById('buildCommand'),
    btnCopyBuildCommand: document.getElementById('btnCopyBuildCommand'),
    btnOutputTab: document.getElementById('btnOutputTab'),
    btnInspectTab: document.getElementById('btnInspectTab'),
    btnBuildTab: document.getElementById('btnBuildTab'),
    progressText: document.getElementById('progressText'),
    progressBarFill: document.getElementById('progressBarFill'),
    btnModeTour: document.getElementById('btnModeTour'),
    btnModePlayground: document.getElementById('btnModePlayground'),
    installModal: document.getElementById('installModal'),
    btnOpenInstall: document.getElementById('btnOpenInstall'),
    btnCloseInstall: document.getElementById('btnCloseInstall')
  };

  // --- Playground Templates ---
  const PLAYGROUND_TEMPLATES = [
    {
      title: '01. Hello, Nyx Studio',
      code: `// A small program you can run immediately in the browser preview
fn main() {
    var name: string = "Nyx Studio"
    print("Hello, " + name)
}

main()`
    },
    {
      title: '02. Safe Navigation & Coalescing',
      code: `// Deterministic null safety in Nyx
fn main() {
    let present: int? = 100
    let missing: int? = null

    // Safe null-coalescing with ??
    let a = present ?? 0
    let b = missing ?? 42

    print($"a: {a}, b: {b}")
}

main()`
    },
    {
      title: '03. RAII Defer Cleanup',
      code: `// Defer executes at scope exit in LIFO order
fn worker() {
    print("1. Worker started")
    defer print("4. First defer (runs last)")
    defer print("3. Second defer (runs first)")
    print("2. Worker doing critical operations...")
}

fn main() {
    worker()
    print("5. Program completed safely")
}

main()`
    },
    {
      title: '04. Pattern Matching',
      code: `// Pattern matching on status codes
fn classify_status(code: int) -> string = match code {
    200 => "200 OK: Request succeeded",
    400 => "400 Bad Request: Malformed syntax",
    404 => "404 Not Found: Resource does not exist",
    500 => "500 Internal Error: Server fault",
    _   => $"HTTP Status {code}"
}

fn main() {
    print(classify_status(200))
    print(classify_status(404))
    print(classify_status(503))
}

main()`
    }
  ];

  const TARGETS = {
    preview: {
      label: 'Browser preview',
      command: null,
      note: 'The browser evaluator can show output for the supported teaching subset. It is not a type checker or a native backend.'
    },
    cpp: {
      label: 'C++20 / native',
      command: (file) => `nyx run ${file} --target cpp`,
      note: 'Build with the stable default native target and inspect the generated binary locally.'
    },
    js: {
      label: 'JavaScript / Node',
      command: (file) => `nyx run ${file} --target js`,
      note: 'Build and run the JavaScript target with the local Nyx CLI and Node.js.'
    },
    wasm: {
      label: 'WebAssembly / bundle',
      command: (file) => `nyx bundle ${file} --target wasm --output build/wasm`,
      note: 'Use the local bundle command to produce the WASM package and its host bindings.'
    },
    llvm: {
      label: 'LLVM IR / experimental',
      command: (file) => `nyx run ${file} --target llvm`,
      note: 'LLVM is experimental. Check the target capability contract before relying on the generated artifact.'
    }
  };

  function populateTemplateSelect() {
    if (!el.templateSelect) return;
    el.templateSelect.innerHTML = '';
    PLAYGROUND_TEMPLATES.forEach((template, index) => {
      const option = document.createElement('option');
      option.value = String(index);
      option.innerText = template.title;
      el.templateSelect.appendChild(option);
    });
    el.templateSelect.value = String(state.playgroundTemplateIndex);
  }

  function selectedTarget() {
    return (el.targetSelect && TARGETS[el.targetSelect.value]) ? el.targetSelect.value : 'preview';
  }

  function setActivePanel(panel) {
    state.activePanel = panel;
    const views = {
      output: el.terminalView,
      inspect: el.inspectionView,
      build: el.buildView
    };
    Object.keys(views).forEach((name) => {
      if (views[name]) views[name].hidden = name !== panel;
    });
    [
      [el.btnOutputTab, 'output'],
      [el.btnInspectTab, 'inspect'],
      [el.btnBuildTab, 'build']
    ].forEach(([button, name]) => {
      if (!button) return;
      const active = name === panel;
      button.classList.toggle('active', active);
      button.setAttribute('aria-selected', String(active));
    });
  }

  function updateBuildGuide() {
    if (!el.buildCommand || !el.buildTargetStatus) return;
    const target = selectedTarget();
    const config = TARGETS[target];
    const filename = (el.editorFilename.innerText || 'scratchpad.nyx').trim();
    el.buildTargetStatus.innerText = config.label;
    if (config.command) {
      el.buildCommand.innerText = config.command(filename);
      el.buildNote.innerHTML = `The browser cannot invoke your local compiler. Save the editor as <code>${escapeHtml(filename)}</code>, then run. ${escapeHtml(config.note)}`;
    } else {
      el.buildCommand.innerText = 'Select a local target to see its command';
      el.buildNote.innerHTML = 'Browser preview is intentionally limited. Select C++, JavaScript, WASM or LLVM to get a local compiler command.';
    }
  }

  function updateTargetUi() {
    const target = selectedTarget();
    const isPreview = target === 'preview';
    const runLabel = document.getElementById('runLabel');
    if (runLabel) runLabel.innerText = isPreview ? 'Run Preview' : 'Show Build';
    el.btnRun.title = isPreview ? 'Run browser preview (Ctrl+Enter)' : 'Show the local build command';
    updateBuildGuide();
  }

  function renderSourceInspection(source) {
    const code = String(source || '');
    const nonEmptyLines = code.split(/\r?\n/).filter((line) => line.trim()).length;
    const functions = (code.match(/\b(?:async\s+)?fn\s+[A-Za-z_][A-Za-z0-9_]*/g) || []).length;
    const imports = (code.match(/^\s*import\b/gm) || []).length;
    const declarations = (code.match(/^\s*(?:let|var|const|struct|enum|type|trait)\b/gm) || []).length;
    const directive = code.match(/^\s*#target\s+([A-Za-z0-9_-]+)/m);
    const sourceTarget = directive ? directive[1] : 'cpp (default)';
    const target = selectedTarget();

    el.sourceStats.innerHTML = [
      ['Lines', nonEmptyLines],
      ['Functions', functions],
      ['Imports', imports],
      ['Declarations', declarations]
    ].map(([label, value]) => `<div class="source-stat"><span class="source-stat-label">${label}</span><strong class="source-stat-value">${value}</strong></div>`).join('');
    el.pipelineTarget.innerText = TARGETS[target].label;
    el.inspectionStatus.innerText = target === 'preview' ? 'Browser analysis' : 'Local build planned';
    el.inspectionNote.innerHTML = `Detected source target: <code>${escapeHtml(sourceTarget)}</code>. This lightweight view counts source constructs; the native compiler remains authoritative for typing, HIR, MIR and backend validation.`;
    setActivePanel('inspect');
  }

  // --- Ace Editor Initialization ---
  function initAce() {
    if (typeof ace === 'undefined') {
      console.warn('Ace not loaded');
      return;
    }

    // Register Nyx Highlighting Mode
    ace.define('ace/mode/nyx_highlight_rules', function (require, exports, module) {
      var oop = require("ace/lib/oop");
      var TextHighlightRules = require("ace/mode/text_highlight_rules").TextHighlightRules;

      var NyxHighlightRules = function () {
        var keywords = "let|var|set|const|fn|struct|enum|type|trait|impl|match|if|elif|else|while|for|in|loop|defer|guard|break|continue|return|throw|try|catch|test|assert|print|import|from|self|mut|and|or|not|null|true|false|Ok|Err";
        var types = "int|float|string|bool|char|byte|void|any|Array|Map|Result|Option";

        this.$rules = {
          "start": [
            { token: "comment", regex: "//.*$" },
            { token: "string.interpolated", regex: '\\$"([^"\\\\]|\\\\.)*"' },
            { token: "string", regex: '".*?"' },
            { token: "string", regex: "'.*?'" },
            { token: "constant.numeric", regex: "0[xX][0-9a-fA-F]+|0[bB][01]+|\\d+(\\.\\d+)?" },
            { token: "keyword.control", regex: "\\b(" + keywords + ")\\b" },
            { token: "support.type", regex: "\\b(" + types + ")\\b" },
            { token: "keyword.operator", regex: "\\|>|\\?\\?|\\?\\.|->|=>|==|!=|<=|>=|\\+=|-=|\\*=|/=|=" }
          ]
        };
      };
      oop.inherits(NyxHighlightRules, TextHighlightRules);
      exports.NyxHighlightRules = NyxHighlightRules;
    });

    ace.define('ace/mode/nyx', function (require, exports, module) {
      var oop = require("ace/lib/oop");
      var TextMode = require("ace/mode/text").Mode;
      var NyxHighlightRules = require("ace/mode/nyx_highlight_rules").NyxHighlightRules;

      var Mode = function () {
        this.HighlightRules = NyxHighlightRules;
      };
      oop.inherits(Mode, TextMode);
      exports.Mode = Mode;
    });

    state.editor = ace.edit("aceEditor");
    state.editor.setTheme("ace/theme/dracula");
    state.editor.session.setMode("ace/mode/nyx");
    state.editor.setOptions({
      enableBasicAutocompletion: true,
      enableLiveAutocompletion: true,
      enableSnippets: true,
      fontFamily: "'JetBrains Mono', 'Fira Code', monospace",
      fontSize: "13.5px",
      tabSize: 4,
      useSoftTabs: true,
      showPrintMargin: false,
      cursorStyle: "smooth",
      wrap: true
    });

    // Custom Nyx Autocompletion
    var langTools = ace.require("ace/ext/language_tools");
    var nyxCompleter = {
      getCompletions: function (editor, session, pos, prefix, callback) {
        var wordList = [
          { caption: "fn", snippet: "fn ${1:name}(${2:params}) -> ${3:void} {\n    $0\n}", meta: "fn" },
          { caption: "let", snippet: "let ${1:name} = ${2:value}", meta: "let" },
          { caption: "var", snippet: "var ${1:name} = ${2:value}", meta: "var" },
          { caption: "set", snippet: "set ${1:target} = ${2:value}", meta: "set" },
          { caption: "struct", snippet: "struct ${1:Name} {\n    ${2:field}: ${3:int}\n}", meta: "struct" },
          { caption: "enum", snippet: "enum ${1:Name} {\n    ${2:Variant}\n}", meta: "enum" },
          { caption: "match", snippet: "match ${1:value} {\n    ${2:pattern} => ${3:result},\n    _ => ${4:default}\n}", meta: "match" },
          { caption: "defer", snippet: "defer ${1:cleanup_fn()}", meta: "defer" },
          { caption: "guard", snippet: "guard ${1:condition} else {\n    return ${2:fallback}\n}", meta: "guard" },
          { caption: "print", snippet: "print(${1:message})", meta: "builtin" },
          { caption: "assert", snippet: "assert(${1:condition}, \"${2:msg}\")", meta: "builtin" },
          { caption: "Ok", snippet: "Ok(${1:value})", meta: "result" },
          { caption: "Err", snippet: "Err(\"${1:error}\")", meta: "result" }
        ];
        callback(null, wordList);
      }
    };
    langTools.addCompleter(nyxCompleter);

    // Keyboard commands inside Ace
    state.editor.commands.addCommand({
      name: 'runCode',
      bindKey: { win: 'Ctrl-Enter', mac: 'Command-Enter' },
      exec: function () {
        runCode();
      }
    });

    state.editor.commands.addCommand({
      name: 'nextExercise',
      bindKey: { win: 'Alt-N', mac: 'Alt-N' },
      exec: function () {
        switchExercise(state.currentExerciseIndex + 1);
      }
    });

    state.editor.commands.addCommand({
      name: 'prevExercise',
      bindKey: { win: 'Alt-P', mac: 'Alt-P' },
      exec: function () {
        switchExercise(state.currentExerciseIndex - 1);
      }
    });

    loadLastOrFirstExercise();
  }

  function getEditorCode() {
    return state.editor ? state.editor.getValue() : '';
  }

  function setEditorCode(val) {
    if (state.editor) {
      state.editor.setValue(val, -1);
    }
  }

  // --- Initialization ---
  function init() {
    // Purge outdated caches from earlier sessions so starter code is 100% fresh and clean
    if (localStorage.getItem('nyx_cache_version') !== CACHE_VERSION) {
      localStorage.removeItem('nyx_tour_code_cache');
      localStorage.removeItem('nyx_tour_completed');
      localStorage.removeItem('nyx_tour_last_index');
      localStorage.setItem('nyx_cache_version', CACHE_VERSION);
      state.userCodeCache = {};
      state.completed = {};
    }

    populateTemplateSelect();
    el.templateSelect.closest('.template-control').style.display = 'none';
    buildExerciseTree();
    setupEventListeners();
    updateProgressUI();
    updateTargetUi();
    setActivePanel('output');
    initAce();
  }

  // --- Build Sidebar Tree ---
  function buildExerciseTree(filterQuery = '') {
    el.exerciseTree.innerHTML = '';
    const query = filterQuery.toLowerCase().trim();

    const groups = {};
    state.exercises.forEach((ex, index) => {
      const match = !query || ex.title.toLowerCase().includes(query) || ex.topic.toLowerCase().includes(query) || ex.id.toLowerCase().includes(query);
      if (!match) return;

      const groupName = ex.topicTitle || ex.topic;
      if (!groups[groupName]) groups[groupName] = [];
      groups[groupName].push({ ex, index });
    });

    Object.keys(groups).forEach(groupName => {
      const groupDiv = document.createElement('div');
      groupDiv.className = 'topic-group';

      const header = document.createElement('div');
      header.className = 'topic-header';
      header.innerText = groupName;
      groupDiv.appendChild(header);

      groups[groupName].forEach(({ ex, index }) => {
        const item = document.createElement('div');
        item.className = 'exercise-item';
        if (index === state.currentExerciseIndex && state.mode === 'tour') {
          item.classList.add('active');
        }
        if (state.completed[ex.id]) {
          item.classList.add('completed');
        }

        const titleSpan = document.createElement('span');
        titleSpan.innerText = `${ex.name}: ${ex.title}`;

        const checkSpan = document.createElement('span');
        checkSpan.className = 'exercise-check';
        checkSpan.innerText = '✓';

        item.appendChild(titleSpan);
        item.appendChild(checkSpan);

        item.addEventListener('click', () => {
          switchExercise(index);
          el.curriculumDrawer.classList.remove('open');
        });

        groupDiv.appendChild(item);
      });

      el.exerciseTree.appendChild(groupDiv);
    });
  }

  // --- Load Exercise ---
  function switchExercise(index) {
    if (index < 0 || index >= state.exercises.length) return;

    // Save previous exercise code IF non-empty
    if (state.editor && state.mode === 'tour') {
      const prevEx = state.exercises[state.currentExerciseIndex];
      const currentCode = getEditorCode();
      if (prevEx && currentCode && currentCode.trim().length > 0) {
        state.userCodeCache[prevEx.id] = currentCode;
        localStorage.setItem('nyx_tour_code_cache', JSON.stringify(state.userCodeCache));
      }
    }

    state.currentExerciseIndex = index;
    const ex = state.exercises[index];

    // Update Header & Lesson UI
    el.badgeTopic.innerText = ex.topicTitle || ex.topic;
    el.exerciseTitle.innerText = `${ex.name}: ${ex.title}`;
    el.exerciseDesc.innerText = ex.description || '';
    el.editorFilename.innerText = `${ex.name}.nyx`;
    el.lessonCounter.innerText = `${index + 1} of ${state.exercises.length}`;

    const isSolved = Boolean(state.completed[ex.id]);
    el.badgeStatus.innerText = isSolved ? '✓ Solved' : 'Unsolved';
    el.badgeStatus.className = 'badge-status' + (isSolved ? ' solved' : '');

    // Compute expected canonical output
    try {
      const solRes = evaluateNyx(ex.solution);
      const expectedText = (solRes.output || []).join('\n').trim();
      el.expectedOutputBox.innerText = expectedText.length > 0 ? expectedText : '(Exercise verifies assertions without stdout)';
    } catch (e) {
      el.expectedOutputBox.innerText = '(Output verified dynamically)';
    }

    // Hints
    el.hintBox.classList.remove('show');
    el.hintBox.innerHTML = '';
    el.hintBtnText.innerText = 'Show Hint';
    if (ex.hints && ex.hints.length > 0) {
      el.btnToggleHint.style.display = 'flex';
      el.hintBox.innerHTML = ex.hints.map((h, i) => `<div><strong>Hint ${i + 1}:</strong> ${escapeHtml(h)}</div>`).join('');
    } else {
      el.btnToggleHint.style.display = 'none';
    }

    // Set Editor Code (fallback to clean starter code)
    const savedCode = state.userCodeCache[ex.id];
    const initialCode = (savedCode && savedCode.trim().length > 0) ? savedCode : ex.code;
    setEditorCode(initialCode);

    // Update active in sidebar
    document.querySelectorAll('.exercise-item').forEach((it, idx) => {
      it.classList.toggle('active', idx === index);
    });

    logTerminal(`[Tour] Loaded exercise: ${ex.name} - ${ex.title}`, 'term-info');
  }

  function loadLastOrFirstExercise() {
    const lastSavedIndex = parseInt(localStorage.getItem('nyx_tour_last_index') || '0', 10);
    switchExercise(isNaN(lastSavedIndex) ? 0 : Math.min(Math.max(lastSavedIndex, 0), state.exercises.length - 1));
  }

  // --- Syntax Pre-Validator for Clear Human Diagnostics ---
  // --- Code Execution & Verification Engine ---
  function runPreview(source) {
    return new Promise((resolve, reject) => {
      const worker = new Worker('preview-worker.js?v=5.0.3-studio-1');
      const timeout = setTimeout(() => {
        worker.terminate();
        reject(new Error('Preview stopped after 2 seconds. Check for an unbounded loop.'));
      }, 2000);
      const finish = () => { clearTimeout(timeout); worker.terminate(); };
      worker.onmessage = ({ data }) => { finish(); resolve(data); };
      worker.onerror = () => { finish(); reject(new Error('Preview could not run. Use the local CLI.')); };
      worker.postMessage(source);
    });
  }

  async function runCode() {
    if (el.btnRun.disabled) return;
    if (selectedTarget() !== 'preview') {
      clearTerminal();
      updateBuildGuide();
      setActivePanel('build');
      el.execStatusBadge.innerText = 'Local CLI required';
      el.execStatusBadge.className = 'status-badge';
      logTerminal(`[Build guide] ${TARGETS[selectedTarget()].label} is not executed in the browser.`, 'term-info');
      return;
    }
    el.btnRun.disabled = true;
    const code = getEditorCode();
    const runMode = state.mode;
    const runIndex = state.currentExerciseIndex;
    clearTerminal();
    logTerminal(`[Previewing: ${el.editorFilename.innerText}]`, 'term-info');

    el.execStatusBadge.innerText = 'Running...';
    el.execStatusBadge.className = 'status-badge';
    setActivePanel('output');

    const startTime = performance.now();
    try {
      const res = await runPreview(code);
      const elapsed = (performance.now() - startTime).toFixed(2);

      if (res.error) {
        el.execStatusBadge.innerText = 'Failed';
        el.execStatusBadge.className = 'status-badge failed';
        logTerminal(`[Error] ${res.error}`, 'term-error');
        logTerminal(`[Hint] Check the code in the editor or click 'Reset' to restore the starter template.`, 'term-hint');
        return;
      }

      res.output.forEach(line => logTerminal(line));

      if (state.mode !== runMode || state.currentExerciseIndex !== runIndex) {
        el.execStatusBadge.innerText = 'Preview finished';
        logTerminal('The exercise changed while running. This output belongs to the previous program.', 'term-info');
        return;
      }

      // Verification in Tour Mode
      if (state.mode === 'tour') {
        verifyTourSolution(code, res.output, elapsed);
      } else {
        el.execStatusBadge.innerText = 'Success';
        el.execStatusBadge.className = 'status-badge passed';
        logTerminal(`\n[Finished in ${elapsed} ms]`, 'term-success');
      }
    } catch (err) {
      el.execStatusBadge.innerText = 'Failed';
      el.execStatusBadge.className = 'status-badge failed';
      logTerminal(`Preview error: ${err.message}`, 'term-error');
    } finally {
      el.btnRun.disabled = false;
    }
  }

  function verifyTourSolution(userCode, userOutput, elapsed) {
    const ex = state.exercises[state.currentExerciseIndex];
    if (!ex) return;

    try {
      const solRes = evaluateNyx(ex.solution);
      const userStr = userOutput.join('\n').trim();
      if (solRes.error) {
        logTerminal('This exercise needs the native compiler; the preview cannot evaluate its reference.', 'term-info');
        el.execStatusBadge.innerText = 'CLI required';
        return;
      }
      const expectedStr = (solRes.output || []).join('\n').trim();

      let passed = false;
      let reason = '';

      if (expectedStr.length > 0) {
        if (userStr === expectedStr) {
          passed = true;
        } else if (userStr.toLowerCase() === expectedStr.toLowerCase()) {
          reason = `Case sensitivity difference!\nExpected: ${JSON.stringify(expectedStr)}\nGot:      ${JSON.stringify(userStr)}\nTip: Check uppercase vs lowercase characters (e.g., 'Tour' vs 'tour').`;
        } else {
          reason = `Output mismatch:\nExpected: ${JSON.stringify(expectedStr)}\nGot:      ${JSON.stringify(userStr)}`;
        }
      } else {
        if (userCode.includes('TODO') || userCode.includes('I AM NOT DONE')) {
          reason = `Exercise contains uncompleted TODO comments. Finish the required task before verifying.`;
        } else {
          reason = 'This exercise has no observable output. Validate it with nyx check / nyx test locally.';
        }
      }

      if (passed) {
        state.completed[ex.id] = true;
        localStorage.setItem('nyx_tour_completed', JSON.stringify(state.completed));
        localStorage.setItem('nyx_tour_last_index', state.currentExerciseIndex);

        el.badgeStatus.innerText = '✓ Solved';
        el.badgeStatus.className = 'badge-status solved';
        el.execStatusBadge.innerText = `Passed (${elapsed}ms)`;
        el.execStatusBadge.className = 'status-badge passed';

        logTerminal(`\nPreview output matches the reference. Compiler validation is still required. (${elapsed} ms)`, 'term-success');
        updateProgressUI();
        buildExerciseTree(el.searchExercises.value);
      } else {
        el.execStatusBadge.innerText = 'Failed';
        el.execStatusBadge.className = 'status-badge failed';
        logTerminal(`\n[Error] Not passed: ${reason}`, 'term-error');
        logTerminal(`[Tip] Review the Objective and Expected Output in the left card.`, 'term-hint');
      }
    } catch (e) {
      logTerminal(`Verification diagnostic: ${e.message}`, 'term-error');
    }
  }

  // --- Limited learning evaluator (see evaluator.js) ---
  function escapeHtml(str) {
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function logTerminal(msg, className = '') {
    const line = document.createElement('div');
    line.className = 'term-line ' + className;
    line.innerText = msg;
    el.terminalView.appendChild(line);
    el.terminalView.scrollTop = el.terminalView.scrollHeight;
  }

  function clearTerminal() {
    el.terminalView.innerHTML = '';
  }

  function updateProgressUI() {
    const total = state.exercises.length;
    const solved = Object.keys(state.completed).length;
    el.progressText.innerText = `${solved} / ${total} Solved`;
    const pct = total > 0 ? (solved / total) * 100 : 0;
    el.progressBarFill.style.width = `${pct}%`;
  }

  // --- Event Listeners ---
  function setupEventListeners() {
    // Run Code
    el.btnRun.addEventListener('click', runCode);

    // Studio inspection and local-build guidance
    el.btnInspect.addEventListener('click', () => renderSourceInspection(getEditorCode()));
    el.btnOutputTab.addEventListener('click', () => setActivePanel('output'));
    el.btnInspectTab.addEventListener('click', () => renderSourceInspection(getEditorCode()));
    el.btnBuildTab.addEventListener('click', () => {
      updateBuildGuide();
      setActivePanel('build');
    });
    el.targetSelect.addEventListener('change', () => {
      updateTargetUi();
      if (selectedTarget() !== 'preview') {
        updateBuildGuide();
      }
    });
    el.templateSelect.addEventListener('change', (event) => {
      const index = Number(event.target.value);
      const template = PLAYGROUND_TEMPLATES[index];
      if (!template) return;
      state.playgroundTemplateIndex = index;
      el.editorFilename.innerText = 'scratchpad.nyx';
      setEditorCode(template.code);
      clearTerminal();
      logTerminal(`[Studio] Loaded example: ${template.title}`, 'term-info');
      updateBuildGuide();
    });
    el.btnCopyBuildCommand.addEventListener('click', async () => {
      const command = el.buildCommand.innerText;
      if (!command || command.startsWith('Select a local target')) return;
      try {
        await navigator.clipboard.writeText(command);
        el.btnCopyBuildCommand.innerText = 'Copied';
        setTimeout(() => { el.btnCopyBuildCommand.innerText = 'Copy'; }, 1200);
      } catch (e) {
        logTerminal('[Build guide] Clipboard access is unavailable. Select the command manually.', 'term-hint');
      }
    });

    // Keyboard Shortcuts
    window.addEventListener('keydown', (e) => {
      if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
        e.preventDefault();
        runCode();
      }
      if (e.altKey && (e.key === 'n' || e.key === 'N')) {
        e.preventDefault();
        switchExercise(state.currentExerciseIndex + 1);
      }
      if (e.altKey && (e.key === 'p' || e.key === 'P')) {
        e.preventDefault();
        switchExercise(state.currentExerciseIndex - 1);
      }
      if (e.key === '/' && document.activeElement !== el.searchExercises && (!state.editor || !state.editor.isFocused())) {
        e.preventDefault();
        el.curriculumDrawer.classList.add('open');
        setTimeout(() => el.searchExercises.focus(), 100);
      }
    });

    // Reset Code
    el.btnResetCode.addEventListener('click', () => {
      if (state.mode === 'playground') {
        const template = PLAYGROUND_TEMPLATES[state.playgroundTemplateIndex];
        if (template && confirm('Reset code to the selected Studio example?')) {
          setEditorCode(template.code);
          logTerminal('[Editor] Code reset to the selected Studio example.', 'term-info');
        }
        return;
      }
      const ex = state.exercises[state.currentExerciseIndex];
      if (ex && confirm('Reset code to original exercise state?')) {
        setEditorCode(ex.code);
        delete state.userCodeCache[ex.id];
        localStorage.setItem('nyx_tour_code_cache', JSON.stringify(state.userCodeCache));
        logTerminal('[Editor] Code reset to default template.', 'term-info');
      }
    });

    // Hints Toggle
    el.btnToggleHint.addEventListener('click', () => {
      const isShowing = el.hintBox.classList.toggle('show');
      el.hintBtnText.innerText = isShowing ? 'Hide Hint' : 'Show Hint';
    });

    // Show Solution
    el.btnShowSolution.addEventListener('click', () => {
      const ex = state.exercises[state.currentExerciseIndex];
      if (ex && confirm('Reveal reference solution in editor?')) {
        setEditorCode(ex.solution);
        logTerminal('[Tour] Reference solution revealed in editor.', 'term-info');
      }
    });

    // Prev / Next Buttons
    el.btnPrevExercise.addEventListener('click', () => {
      switchExercise(state.currentExerciseIndex - 1);
    });
    el.btnNextExercise.addEventListener('click', () => {
      switchExercise(state.currentExerciseIndex + 1);
    });

    // Curriculum Drawer Open / Close
    el.btnToggleDrawer.addEventListener('click', () => {
      el.curriculumDrawer.classList.add('open');
      setTimeout(() => el.searchExercises.focus(), 100);
    });
    el.btnCloseDrawer.addEventListener('click', () => {
      el.curriculumDrawer.classList.remove('open');
    });

    // Search Filter
    el.searchExercises.addEventListener('input', (e) => {
      buildExerciseTree(e.target.value);
    });

    // Resizer Divider
    let isDragging = false;
    el.paneResizer.addEventListener('mousedown', () => {
      isDragging = true;
      document.body.style.cursor = 'row-resize';
      document.body.style.userSelect = 'none';
    });
    window.addEventListener('mousemove', (e) => {
      if (!isDragging) return;
      const rightPaneRect = document.querySelector('.right-pane').getBoundingClientRect();
      const newHeight = rightPaneRect.bottom - e.clientY;
      if (newHeight > 80 && newHeight < rightPaneRect.height - 120) {
        el.terminalSection.style.height = `${newHeight}px`;
        if (state.editor) state.editor.resize();
      }
    });
    window.addEventListener('mouseup', () => {
      if (isDragging) {
        isDragging = false;
        document.body.style.cursor = '';
        document.body.style.userSelect = '';
        if (state.editor) state.editor.resize();
      }
    });

    el.btnClearTerminal.addEventListener('click', clearTerminal);

    // Modes: Tour vs Playground
    el.btnModeTour.addEventListener('click', () => {
      state.mode = 'tour';
      el.btnModeTour.classList.add('active');
      el.btnModePlayground.classList.remove('active');
      el.templateSelect.closest('.template-control').style.display = 'none';
      el.leftPane.style.display = 'flex';
      switchExercise(state.currentExerciseIndex);
      if (state.editor) setTimeout(() => state.editor.resize(), 100);
    });

    el.btnModePlayground.addEventListener('click', () => {
      state.mode = 'playground';
      el.btnModePlayground.classList.add('active');
      el.btnModeTour.classList.remove('active');
      el.templateSelect.closest('.template-control').style.display = 'inline-flex';
      el.leftPane.style.display = 'none';

      const tmpl = PLAYGROUND_TEMPLATES[state.playgroundTemplateIndex];
      el.editorFilename.innerText = 'scratchpad.nyx';
      setEditorCode(tmpl.code);
      updateBuildGuide();
      if (state.editor) setTimeout(() => state.editor.resize(), 100);
    });

    // Install Modal
    el.btnOpenInstall.addEventListener('click', () => el.installModal.classList.add('open'));
    el.btnCloseInstall.addEventListener('click', () => el.installModal.classList.remove('open'));
    el.installModal.addEventListener('click', (e) => {
      if (e.target === el.installModal) el.installModal.classList.remove('open');
    });
  }

  // Run on DOM ready
  document.addEventListener('DOMContentLoaded', init);
})();
