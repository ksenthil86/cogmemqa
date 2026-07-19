"use client";

import { Component, type ReactNode } from "react";

interface Props {
  /** Panel name shown in the error card. */
  label: string;
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Per-panel error boundary (pattern from the create-context-graph scaffold):
 * a crash in one panel (e.g. NVL/WebGL) renders an error card with a reset
 * button instead of blanking the whole app.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <section
          data-testid="panel-error"
          className="flex min-w-0 flex-1 flex-col items-center justify-center gap-3 border-r border-gray-200 bg-white p-6 text-center"
        >
          <p className="text-sm font-semibold text-gray-900">
            {this.props.label} crashed
          </p>
          <p className="max-w-xs break-words text-xs text-gray-500">
            {this.state.error.message}
          </p>
          <button
            onClick={() => this.setState({ error: null })}
            className="rounded-lg border border-gray-300 bg-white px-3 py-1.5 text-sm text-gray-700 transition hover:bg-gray-50"
          >
            Reset panel
          </button>
        </section>
      );
    }
    return this.props.children;
  }
}
