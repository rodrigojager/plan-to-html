# Decisões de arquitetura

Kind: decisions. As escolhas que sustentam a experiência.

Part of [PLAN.md](PLAN.md).

## ADR-1: Markdown como fonte

O plano precisa continuar simples de editar, revisar e entregar a agentes. Os arquivos Markdown são a fonte de verdade e o HTML é uma representação produzida por código; isso permite reconstruir a interface sem gerar novamente o corpo do conteúdo.

## ADR-2: Dois temas, uma interface

A leitura acontece em ambientes e dispositivos diferentes. Claro e escuro compartilham a mesma estrutura e controles, com cores semânticas adaptadas para texto, superfícies e diagramas.

## ADR-3: Incrementos separados

Os visuais explicativos podem evoluir sem modificar a prosa do plano. A configuração separada mantém esse trabalho pequeno e permite reaproveitá-lo quando os arquivos de origem mudam.
