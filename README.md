# Zek Download

Baixe **vídeos e músicas** de milhares de sites com uma interface simples e profissional.
Usa o [yt-dlp](https://github.com/yt-dlp/yt-dlp) por baixo — e **se mantém atualizado sozinho**.

## Instalar

**Linux Mint / Ubuntu / Debian**
```bash
sudo apt install ./zek-download_1.1.0_all.deb
```
**Fedora**
```bash
sudo dnf install ./zek-download-1.1.0-1.noarch.rpm
```
Depois abra **Zek Download** no menu de aplicativos (ou rode `zek-download`). Na primeira vez ele baixa o motor de
download (poucos segundos) — precisa de internet.

> Fedora: o `ffmpeg` completo vem do RPM Fusion; o `ffmpeg-free` dos repositórios oficiais já resolve a dependência.
> YouTube: instale também o `nodejs` (já é "Recomendado" no pacote) — o yt-dlp usa para decifrar os links.

## Como usar
1. **Cole o link** (ou arraste para a janela).
2. Escolha **Vídeo** (qualidade) ou **Áudio** (MP3, M4A, Opus, FLAC).
3. Clique em **Baixar**. Acompanhe porcentagem, velocidade e tempo restante; ao terminar, abra o arquivo ou a pasta.

Dá para colar vários links de uma vez (viram uma fila) e baixar playlists inteiras.

## Como ele "se adapta" quando o yt-dlp muda
- **Não embute o yt-dlp.** Baixa o executável oficial para `~/.local/share/zek-download/bin` e confere o SHA-256.
- **Atualiza sozinho** ao abrir (no máx. a cada 6 h) e pelo menu → *Verificar atualização do motor*.
- **Autocura:** se um download falhar com sinais de "site mudou" (extractor quebrado, 403, formato indisponível…),
  o Zek Download atualiza o motor e **tenta de novo automaticamente**, sem você fazer nada.
- O app só passa **opções estáveis** do yt-dlp e lê o progresso por templates (`--progress-template`), que mudam
  muito pouco. Se uma opção sumir numa versão futura, o app faz fallback quando possível.
- Se a versão estável ainda não corrigiu, ative o canal **Nightly** em Configurações.

Ou seja: **você não precisa publicar uma nova versão do Zek Download a cada atualização do yt-dlp.**
Só será preciso mexer no Zek Download se o yt-dlp mudar o *formato dos argumentos/saída* de forma incompatível.

## Desenvolvimento
```bash
./build.sh                 # testes + gera dist/*.deb e dist/*.rpm
python3 tests/test_core.py # só os testes
```
Estrutura: `engine.py` (motor/atualização), `downloader.py` (links, argumentos, progresso, erros),
`manager.py` (fila + autocura), `app.py` (interface GTK 3), `settings.py`, `style.py` (tema).
Plano B no Fedora: `rpmbuild -bb --build-in-place packaging/zek-download.spec`.

Use apenas para conteúdo que você tem direito de baixar. Veja `SECURITY.md` para detalhes de segurança.
Licença: MIT.
