# Gyroflow Auto — by Paroneto

Pluga o cartão da **GoPro** ou da **DJI O4 Pro** → copia → junta os arquivos cortados → estabiliza no Gyroflow. Sozinho.

## ⬇️ Baixar

**[Clique aqui para baixar o GyroflowAuto_by_Paroneto.zip](https://github.com/yuriparonetto-cyber/gyroflow-auto/releases/latest/download/GyroflowAuto_by_Paroneto.zip)**

Funciona no **Mac** e no **Windows**. Precisa ter o [Gyroflow](https://gyroflow.xyz/download) instalado antes.

## Como instalar

- **Mac:** abra a pasta `Mac` e dê dois cliques em `Instalar Gyroflow Auto.command`.
  Se o Mac bloquear: botão direito > Abrir > Abrir.
- **Windows:** extraia o zip, abra a pasta `Windows` e dê dois cliques em `Instalar Gyroflow Auto.bat`.
  Se aparecer "O Windows protegeu o computador": Mais informações > Executar assim mesmo.

O instalador baixa sozinho o Python, o ffmpeg e o mp4_merge. O guia completo está no [LEIA-ME.txt](LEIA-ME.txt).

## O que ele faz

- Copia os vídeos novos para um cache (nunca estabiliza direto do cartão).
- Junta os arquivos que a O4 corta no meio, só quando tem certeza.
- Estabiliza na mesma resolução e fps da gravação, em MP4 H.265 10-bit, mantendo o Log e os metadados.
- Salva em `Área de Trabalho/<Nome do Evento>/` e lembra o que já foi feito.
- Só pergunta o nome do evento quando o evento é novo.
- Cor (LUT + look FUJI CLÁSSICO 50%) **só quando você pede**.

> A versão Windows ainda está em teste. Se der erro, mande o arquivo `%LOCALAPPDATA%\GyroflowAuto\GyroflowAuto.log`.

Feito por Yuri Paroneto
