# Sueth Archy Studio — 0.1.0

Ferramenta desktop local, independente do CX Forge, para desenvolvedores Genesys Cloud Architect. Não é um produto oficial da Genesys.

## Rodar no Windows

Pré-requisitos: Python 3.12, Archy instalado e access token da organização de destino. Se o Archy não estiver no PATH, selecione o `archy.exe` nativo na interface. Launchers `.cmd`/`.bat` não são suportados nesta versão.

```powershell
powershell -ExecutionPolicy Bypass -File .\start.ps1
```

Ou manualmente, sem ativar o ambiente virtual:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

Selecione região, tipo de token, access token e YAML. Clique em Validar, Criar ou Publicar. A organização é determinada pelo token; região não identifica uma organização. Confirme a operação de escrita antes de enfileirá-la. Não use produção no primeiro teste.

## Escopo

- Detecção do executável e versão; suporte a user access token e client credentials access token já emitidos.
- Comandos nativos `validateYaml`, `create`, `publish`; sem motor de validação próprio. A validação YAML não garante publicação nem validação completa de dependências remotas.
- `QProcess` assíncrono, fila FIFO em memória, pausa após falha, remoção de pendentes, nenhuma repetição automática. Uma instância do Studio por vez; não controla outros processos Archy externos.
- Console por execução, stdout/stderr unificados, JSON de resultado quando suportado, cópia e exportação TXT. Histórico SQLite apenas de metadados; status é baseado no exit code, não em confirmação independente da API.
- Antes de cada execução consulta `archy <comando> --help` e exige os parâmetros de autenticação e arquivo esperados. Se a versão não os anuncia, bloqueia. Isso não comprova semântica/precedência de todas as opções nem compatibilidade real.
- O YAML original não é editado pelo Studio; SHA-256 verificado antes de iniciar. Arquivos dependentes e alterações após a checagem não são congelados. Não modifique o projeto YAML enquanto estiver na fila ou executando.
- Não há autenticação automática, refresh token, exportação de fluxos, editor YAML, nem distribuição binária neste MVP.

## Segurança e homologação

O token fica em memória na interface e na fila, e em um arquivo de opções temporário (texto puro) somente durante a execução. Não é passado como argumento de linha de comando, nem armazenado no SQLite ou nas preferências. Em Unix o arquivo usa modo 0600; no Windows depende das ACLs do diretório temporário do usuário. A limpeza ocorre ao finalizar normalmente; encerramento forçado, queda ou falha de limpeza podem deixar arquivos. Revogue o token e remova diretórios `sueth-archy-*` residuais se necessário. Tokens em memória Python não são apagados de modo criptograficamente garantido. A aplicação mascara tokens conhecidos e alguns campos sensíveis no console; revise logs antes de compartilhar. O próprio Archy pode gerar logs/configurações fora do controle do Studio. Não configure debug ou credenciais persistentes para homologação; use configuração Archy limpa, sem opções de escrita perigosas. O Studio tenta sobrescrever `recreate`, `forceUnlock`, `debugPublish` e `debug` com false quando anunciados pelo CLI; a precedência real precisa de homologação. O Studio não bloqueia operações com base em regras duplicadas de nomes e não tenta rollback remoto.

Primeiro teste em organização de homologação:

1. `archy --version`, `archy validateYaml --help`, `archy create --help`, `archy publish --help`.
2. Verificar validação de YAML correto e inválido com ambos os tipos de token.
3. Testar CREATE de fluxo novo e PUBLISH com um fluxo descartável; conferir estado no Architect.
4. Testar token expirado, falta de permissão, duplicidade e dependência ausente; conferir fila pausada e estado remoto.
5. Inspecionar logs, arquivos temporários e histórico para assegurar tratamento das credenciais.

## Desenvolvimento

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
```

CI em Windows e Linux, com testes sem chamadas reais ao Genesys. O teste de QProcess utiliza um processo Python simulando o Archy. A interface usa apenas PySide6 Essentials. Dados locais ficam no AppLocalDataLocation do Qt; configurações não sensíveis em QSettings. A fila não é restaurada entre sessões.

## Licenças

Código próprio MIT (arquivo LICENSE). PySide6 Essentials/Qt possuem opções LGPLv3/GPLv3/comercial; este projeto usa apenas Qt Core, GUI e Widgets. A licença MIT não substitui as obrigações das dependências. A distribuição inicial é em código-fonte, com dependências instaladas pelo pip. Antes de distribuir binários, conferir obrigações LGPLv3, licenças de terceiros, avisos, código-fonte correspondente, possibilidade de substituir bibliotecas e documentação. Preferir distribuição em pasta (`--onedir`) para facilitar substituição; isso por si só não assegura conformidade. Archy não é incluído.

- https://doc.qt.io/qtforpython-6/
- https://www.qt.io/development/open-source-lgpl-obligations
- https://developer.genesys.cloud/devapps/archy/commandOverview

## Roadmap

- 0.1.1: homologação real com Archy, revisão de compatibilidade e segurança de credenciais, testes de GUI.
- 0.2: exportação de fluxos, perfis de organizações sem segredos, validação em lote.
- 0.3: editor YAML, diff, integração Git e instalador Windows após revisão de licenças.
