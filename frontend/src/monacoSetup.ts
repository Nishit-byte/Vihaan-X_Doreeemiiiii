// Bundles Monaco locally (no CDN) so the demo works if venue Wi-Fi drops.
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api'
import 'monaco-editor/esm/vs/basic-languages/python/python.contribution'
import 'monaco-editor/esm/vs/basic-languages/cpp/cpp.contribution'
import 'monaco-editor/esm/vs/basic-languages/java/java.contribution'
import 'monaco-editor/esm/vs/basic-languages/typescript/typescript.contribution'
import 'monaco-editor/esm/vs/basic-languages/javascript/javascript.contribution'
import 'monaco-editor/esm/vs/basic-languages/go/go.contribution'
import 'monaco-editor/esm/vs/basic-languages/rust/rust.contribution'
import 'monaco-editor/esm/vs/basic-languages/markdown/markdown.contribution'
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import { loader } from '@monaco-editor/react'

;(self as any).MonacoEnvironment = { getWorker: () => new EditorWorker() }
loader.config({ monaco })

// Quizlet clean light theme for Monaco Editor
monaco.editor.defineTheme('vivavoce', {
  base: 'vs',
  inherit: true,
  rules: [
    { token: '', foreground: '282e3e' },
    { token: 'comment', foreground: '939bb4', fontStyle: 'italic' },
    { token: 'keyword', foreground: '4255ff', fontStyle: 'bold' },
    { token: 'string', foreground: '0891b2' },
    { token: 'number', foreground: '7c3aed' },
    { token: 'type', foreground: '2e3856' },
  ],
  colors: {
    'editor.background': '#ffffff',
    'editor.foreground': '#282e3e',
    'editor.lineHighlightBackground': '#f6f7fb',
    'editor.selectionBackground': '#dbdfff',
    'editorLineNumber.foreground': '#939bb4',
    'editorLineNumber.activeForeground': '#282e3e',
    'editorCursor.foreground': '#4255ff',
    'editorGutter.background': '#ffffff',
    'editorWidget.background': '#ffffff',
    'editorWidget.border': '#d9dde8',
    'scrollbarSlider.background': '#d9dde888',
    'scrollbarSlider.hoverBackground': '#939bb4aa',
  },
})

export { monaco }
