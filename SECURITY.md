# Segurança no Zek Download

## Como o motor (yt-dlp) é obtido
- Baixado **somente** de `https://github.com/yt-dlp/...` (releases oficiais). Qualquer redirecionamento para
  `http://` é bloqueado e os certificados TLS são verificados.
- O `SHA2-256SUMS` da release é baixado e o binário só é instalado se o SHA-256 **conferir**.
- O binário novo é testado (`--version`) **antes** de substituir o antigo. Se algo falhar, a versão que já
  funcionava continua no lugar.
- Instalação em `~/.local/share/zek-download/bin` (pasta 0700, do usuário). Nenhum `sudo` em tempo de execução.
- Limite de tamanho nos downloads de atualização (listas 256 KB, binário 250 MB).

**Limite honesto:** o checksum vem da mesma release do binário. Ele protege contra corrupção, adulteração em
trânsito e arquivos trocados, mas não contra um comprometimento da própria conta do yt-dlp no GitHub.
(Melhoria futura possível: verificar a assinatura GPG `SHA2-256SUMS.sig`.)

## Execução
- O yt-dlp roda **sem shell**, com lista de argumentos; o link vai depois de `--` (nunca vira opção).
- Só aceita links `http://` e `https://`; rejeita espaços, caracteres de controle e links gigantes.
- `--ignore-config`: arquivos de configuração do usuário (que poderiam ter `--exec`) são ignorados.
- Opções (qualidade, formato, navegador de cookies) são validadas contra listas fixas.
- Launcher em modo isolado do Python (`-I`): ignora `PYTHONPATH` e pacotes do site do usuário.
- Configurações em `~/.config/zek-download/settings.json` com permissão 0600, validadas ao carregar.
- Cookies do navegador só são usados se você escolher um navegador em Configurações, e nunca são copiados/guardados.

## Reportar problema
Abra uma issue privada/security advisory no repositório.
