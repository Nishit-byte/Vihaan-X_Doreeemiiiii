# VivaVoce — Project Description

## Overview

VivaVoce is an adaptive learning and technical interview practice platform built for students preparing to explain their software projects, solve data structures and algorithms (DSA) problems, and understand technical research papers.

Instead of relying solely on static quizzes or ungrounded chat, VivaVoce ties every interaction to concrete artifacts—source files from a GitHub repository, test-verified code solutions in an in-browser editor, or page-cited passages from an uploaded PDF.

## Problem Addressed

1. **Passive Project & Interview Preparation:** Students often struggle to defend *why* a function was implemented a certain way, how edge cases behave, or what trade-offs exist in their own repositories during live technical vivas and interviews.
2. **Surface-Level DSA Drilling:** Standard problem sheets check final pass/fail output without probing time/space complexity reasoning or guiding iterative refinement interactively.
3. **Dense Technical Research Papers:** Students reading unfamiliar papers struggle to separate core contributions and method steps from dense prose or verify claims back to exact source pages.

## Core Modes

- **Practice Interview (Repository Viva):** Ingests a GitHub repository (or offline sample repository), indexes source files via Python AST parsing and contributor metadata where available, highlights relevant line ranges in Monaco Editor, and conducts a voice- or text-driven adaptive interview across L1 Recall, L2 Comprehension, L3 Analysis, and L4 Evaluation.
- **Coding Practice (DSA Prep):** Provides starter problems and test suites in an interactive code editor, executes bounded test verification (`pytest` subprocess runner), and guides complexity and edge-case discussion.
- **Research Paper Explorer:** A dedicated, non-interview study workspace that extracts text and layout per page from an uploaded PDF (or cached sample paper), separates metadata from PDF watermarks/furniture, presents an Overview and Full Breakdown with plain-language vs. author-statement distinction, renders grounded method-pipeline and story-map visuals, and opens verifiable source excerpts with exact page numbers on click.

## Technical Summary

- **Frontend:** React, TypeScript, Vite, Tailwind CSS, Monaco Editor, Mermaid, and Recharts.
- **Backend:** Python modular monolith with FastAPI and Pydantic schemas (`backend/main.py`, `backend/models/schemas.py`).
- **Analysis & Execution:** GitPython, Python `ast`, PyMuPDF, and a time-bounded subprocess verification runner.
- **AI & Voice (Optional / Fallback-Ready):** Gemini API for adaptive question/explanation generation, Groq Whisper for speech-to-text, Edge TTS (with optional ElevenLabs) for speech synthesis, and deterministic/demo fallbacks when offline or unconfigured.
