# plan-to-html

Skill para converter um ou vários arquivos Markdown em um leitor HTML com navegação, busca, imagens, diagramas e modo claro/escuro. A conversão, as classes e os estilos são aplicados por código Python. O conteúdo original permanece disponível; a IA participa apenas dos incrementos visuais que exigem interpretação.

O resultado pode ser um HTML autocontido, que abre por `file://` e funciona offline, com CSS, JavaScript, imagens e fontes incorporados.

## Instalação

Requer Python 3.10 ou superior com `pip`. Clone o repositório no diretório de skills do agente que pretende usar:

| Agente | Diretório de destino |
| --- | --- |
| Codex | `~/.codex/skills/plan-to-html` |
| Claude Code | `~/.claude/skills/plan-to-html` |
| OpenCode | `~/.config/opencode/skills/plan-to-html` |

Exemplo para Codex:

```sh
git clone https://github.com/rodrigojager/plan-to-html.git ~/.codex/skills/plan-to-html
cd ~/.codex/skills/plan-to-html
python scripts/setup.py
```

O setup baixa dependências com versões fixadas e as instala em `.vendor/`, sem alterar os pacotes globais do Python. Depois dessa preparação, a geração normal funciona offline. As fontes, suas licenças e o bundle do Mermaid já acompanham o repositório; `python scripts/setup.py --skip-mermaid` evita baixar novamente esse bundle.

Para compartilhar a mesma instalação entre agentes, vincule os outros diretórios à pasta clonada. O ponto de entrada é [SKILL.md](SKILL.md), com o nome `plan-to-html`. Abra uma nova sessão do agente se a skill ainda não aparecer.

## Uso

No agente, peça para usar `plan-to-html` e indique o arquivo ou a pasta do plano. No Codex, também é possível invocá-la como `$plan-to-html`.

Os comandos abaixo partem da raiz desta skill. Os caminhos de entrada e saída podem apontar para qualquer pasta de trabalho.

```sh
# Gerar diretamente um arquivo autocontido.
python scripts/plan_html.py build caminho/PLAN.md --output output/plano.html --theme papel --format single

# Usar o exemplo incluído.
python scripts/plan_html.py build examples/reading-plan --output output/exemplo.html --theme neon-laser --format single
```

Para personalizar CSS, JavaScript ou visuais antes de incorporar os recursos, use duas etapas:

```sh
python scripts/plan_html.py scan caminho/PLAN.md --output output/outline.json
python scripts/plan_html.py build caminho/PLAN.md --output work/plano.html --theme manuscrito
# Ajuste os recursos da versão editável, se necessário.
python scripts/bundle_html.py work/plano.html --output output/plano.html
```

O primeiro HTML mantém recursos separados para edição. O empacotador lê suas referências finais e incorpora os arquivos locais, incluindo SVG, PNG, BMP, fontes, CSS e JavaScript. Recursos estáticos ausentes ou externos interrompem o empacotamento por padrão. Links comuns para sites continuam sendo links.

Imports de módulos JavaScript adicionais podem usar o bundler opcional, instalado com `python scripts/setup.py --with-js-bundler` — essa opção requer Node.js e npm. A geração padrão dispensa Node.js.

## Recursos

- Navegação entre documentos e seções, busca e links diretos para trechos.
- Modo claro/escuro, preferências de leitura, posição salva, layout responsivo e impressão.
- Código com destaque, cópia e controle de quebra de linhas; tabelas com cabeçalhos fixos.
- Imagens ampliáveis, diagramas Mermaid e visuais adicionais descritos em um pequeno JSON.
- Mapa dos links entre documentos: foco em um documento mostra seus vizinhos diretos e oculta os demais. As conexões passam por corredores entre os cartões, com verificação de colisões; mapas densos mostram linhas sob demanda.
- Conversão determinística do Markdown, sem reescrever o corpo com IA ou acrescentar slogans e introduções promocionais.

## Temas e prévia

Abra [preview.html](preview.html) após baixar o arquivo ou clonar o repositório. A prévia é autocontida e permite percorrer 20 temas, com modo claro/escuro. **O seletor existe apenas nesse exemplo**; os HTMLs normais recebem o tema escolhido antes da geração.

Temas incluídos: `papel`, `grafite`, `carbono`, `jade`, `prisma`, `caderno`, `coral`, `studio`, `iris`, `polar`, `neon-laser`, `manuscrito`, `crayon`, `papiro`, `jornal`, `moderno`, `minimalista`, `maximalista`, `art-deco` e `terminal`. Também estão disponíveis `default` e `slate`.

É possível colocar um CSS compatível em `themes/` e selecionar `--theme NOME`, ou passar seu caminho diretamente. O [contrato dos temas](references/themes.md) separa aparência, estrutura e comportamento para permitir mudanças sem reescrever o renderizador.

## Referências

| Arquivo | Conteúdo |
| --- | --- |
| [SKILL.md](SKILL.md) | Fluxo do agente e regras editoriais |
| [content-visuals.md](references/content-visuals.md) | Quando acrescentar gráficos, fluxogramas, linhas do tempo e outros visuais |
| [enhancements.md](references/enhancements.md) | Formato dos incrementos visuais |
| [themes.md](references/themes.md) | Variáveis, organização e contrato dos temas |
| [reading-map.md](references/reading-map.md) | Interação e roteamento do mapa de leitura |
| [packaging.md](references/packaging.md) | Empacotamento offline e recursos adicionais |
| [Exemplo de temas](examples/theme-preview/README.md) | Pesquisa de referências, geração e testes da prévia |

## Verificação

```sh
python scripts/check_renderer.py
```

As verificações no navegador usam Playwright. Para executá-las, instale `playwright` no ambiente Python de desenvolvimento e execute `python -m playwright install chromium`. Os testes de empacotamento com imports também precisam do setup com `--with-js-bundler`.

```sh
python scripts/check_bundle.py
python scripts/check_reader_tools.py
python scripts/check_reading_map.py
python scripts/check_browser.py
```

Os testes cobrem preservação da fonte, recursos incorporados, controles, mapa de leitura, modo claro/escuro, telas menores e funcionamento sem rede. Os scripts criam arquivos temporários ou usam `.test-output/`.

## Dependências e referências visuais

As dependências Python estão fixadas em [requirements.txt](requirements.txt). O Mermaid e as fontes locais mantêm suas licenças em `assets/vendor/` e `assets/fonts/`.

A pesquisa visual dos temas utilizou [design-inspiration-mcp](https://github.com/notsointresting/design-inspiration-mcp). Os registros e a [licença dessa referência](examples/theme-preview/DESIGN-INSPIRATION-MCP-LICENSE.txt) estão junto ao exemplo. Esse MCP e suas dependências são opcionais para repetir a pesquisa; não são usados para gerar ou abrir o HTML.
