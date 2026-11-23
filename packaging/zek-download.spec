# Plano B: build nativo no Fedora ->  rpmbuild -bb --build-in-place packaging/zek-download.spec
%global debug_package %{nil}
Name:           zek-download
Version:        1.1.1
Release:        1%{?dist}
Summary:        Baixador de vídeos e músicas de vários sites
License:        MIT
URL:            https://github.com/aaaiiicerol
BuildArch:      noarch
Requires:       /usr/bin/python3
Requires:       python3-gobject
Requires:       gtk3
Requires:       ca-certificates
# ffmpeg/ffmpeg-free necessário para mesclar vídeo e áudio.
# No Fedora, ffmpeg-free vem nos repositórios oficiais; o ffmpeg completo fica no RPM Fusion.
Recommends:     ffmpeg-free
Recommends:     nodejs

%description
O Zek Download baixa vídeos e músicas de milhares de sites usando o yt-dlp, com
interface simples e progresso em tempo real. O motor de download é atualizado
automaticamente (com verificação SHA-256) para continuar funcionando quando
os sites mudam.

%build

%install
install -Dm755 packaging/zek-download %{buildroot}%{_bindir}/zek-download
install -d %{buildroot}%{_prefix}/lib/zek-download/zekdl
install -m644 src/zekdl/*.py %{buildroot}%{_prefix}/lib/zek-download/zekdl/
install -Dm644 packaging/io.github.aaaiiicerol.ZekDownload.desktop %{buildroot}%{_datadir}/applications/io.github.aaaiiicerol.ZekDownload.desktop
install -Dm644 packaging/io.github.aaaiiicerol.ZekDownload.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/io.github.aaaiiicerol.ZekDownload.svg
install -Dm644 README.md %{buildroot}%{_docdir}/zek-download/README.md
install -Dm644 LICENSE %{buildroot}%{_licensedir}/zek-download/LICENSE

%files
%license LICENSE
%doc README.md
%{_bindir}/zek-download
%{_prefix}/lib/zek-download
%{_datadir}/applications/io.github.aaaiiicerol.ZekDownload.desktop
%{_datadir}/icons/hicolor/scalable/apps/io.github.aaaiiicerol.ZekDownload.svg
