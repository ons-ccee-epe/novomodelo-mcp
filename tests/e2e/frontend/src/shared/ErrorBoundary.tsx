import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}

interface State {
  error: Error | null;
}

/**
 * Captura erros de render em runtime e mostra a mensagem em vez de deixar a
 * pagina em branco. Uma tela branca muda esconde a causa; aqui a causa fica
 * visivel (e no console).
 */
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("[dashboard] erro de render:", error, info.componentStack);
  }

  render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="nm-shell">
        <div className="nm-banner" data-kind="critical">
          <strong>O dashboard falhou ao renderizar.</strong>
          <pre className="nm-error-message">{error.message}</pre>
          <div className="nm-banner-note">
            Veja o console do navegador (F12) para o stack completo.
          </div>
        </div>
      </div>
    );
  }
}
