// Bundles Monaco locally (no CDN) so the demo works if venue Wi-Fi drops.
import * as monaco from 'monaco-editor/esm/vs/editor/editor.api'
import 'monaco-editor/esm/vs/basic-languages/python/python.contribution'
import 'monaco-editor/esm/vs/basic-languages/typescript/typescript.contribution'
import 'monaco-editor/esm/vs/basic-languages/javascript/javascript.contribution'
import 'monaco-editor/esm/vs/basic-languages/markdown/markdown.contribution'
import EditorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker'
import { loader } from '@monaco-editor/react'

;(self as any).MonacoEnvironment = { getWorker: () => new EditorWorker() }
loader.config({ monaco })

monaco.editor.defineTheme('vivavoce', {
  base: 'vs-dark',
  inherit: true,
  rules: [
    { token: '', foreground: 'e2e8f0' },
    { token: 'comment', foreground: '64748b' },
    { token: 'keyword', foreground: '00dc82' },
    { token: 'string', foreground: 'fb848e' },
    { token: 'number', foreground: 'a156fe' },
    { token: 'type', foreground: '90a1b9' },
  ],
  colors: {
    'editor.background': '#080e21',
    'editor.foreground': '#e2e8f0',
    'editor.lineHighlightBackground': '#0f172b',
    'editor.selectionBackground': '#1d293d',
    'editorLineNumber.foreground': '#314158',
    'editorLineNumber.activeForeground': '#90a1b9',
    'editorCursor.foreground': '#00dc82',
    'editorGutter.background': '#080e21',
    'editorWidget.background': '#0f172b',
    'scrollbarSlider.background': '#1d293d99',
  },
})

export { monaco }
