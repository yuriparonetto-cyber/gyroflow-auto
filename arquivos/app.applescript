-- Gyroflow Auto: app aberto no Dock = ligado. Fechar (⌘Q) = desligado.
on basePath()
	return (POSIX path of (path to home folder)) & "Library/Application Support/GyroflowAuto/"
end basePath

on isRunning()
	set pidf to basePath() & "gyroflow_auto.pid"
	return (do shell script "f=" & quoted form of pidf & "; if [ -f \"$f\" ] && kill -0 $(cat \"$f\") 2>/dev/null; then echo sim; else echo nao; fi") is "sim"
end isRunning

on startDaemon()
	if not isRunning() then
		do shell script "cd /tmp; /usr/bin/nohup __PYTHON__ -u " & quoted form of (basePath() & "gyroflow_auto.py") & " >>$HOME/Library/Logs/GyroflowAuto.err 2>&1 &"
	end if
end startDaemon

on run
	startDaemon()
end run

on idle
	-- se o motor cair por algum motivo, religa sozinho
	startDaemon()
	return 20
end idle

on getSmooth()
	return do shell script "__PYTHON__ -c \"import json,os;p=os.path.expanduser('~/Library/Application Support/GyroflowAuto/config.json');print(json.load(open(p)).get('suavidade_pct',30) if os.path.exists(p) else 30)\""
end getSmooth

on setSmooth(v)
	do shell script "__PYTHON__ -c \"import json,os;p=os.path.expanduser('~/Library/Application Support/GyroflowAuto/config.json');d=json.load(open(p)) if os.path.exists(p) else {};d['suavidade_pct']=" & v & ";json.dump(d,open(p,'w'),indent=2,ensure_ascii=False)\""
end setSmooth

on reopen
	set statusTxt to "LIGADO — esperando cartão."
	if not isRunning() then set statusTxt to "Religando…"
	set sm to getSmooth()
	set logTail to do shell script "tail -n 6 ~/Library/Logs/GyroflowAuto.log | cut -c12-110 || true"
	set r to display dialog "Gyroflow Auto está " & statusTxt & return & "Suavidade: " & sm & "%   •   Cor: só quando você pedir" & return & return & "Últimos eventos:" & return & logTail & return & return & "Para DESLIGAR: feche o app (⌘Q ou botão direito no Dock → Encerrar)." buttons {"Ver log", "Opções…", "OK"} default button "OK" with title "Gyroflow Auto"
	set b to button returned of r
	if b is "Ver log" then
		do shell script "open -a Console ~/Library/Logs/GyroflowAuto.log"
	else if b is "Opções…" then
		set opts to {"Aplicar COR (LUT + Fuji 50%) numa pasta…", "Suavidade 30% (padrão)", "Suavidade 50%"}
		set c to choose from list opts with title "Gyroflow Auto" with prompt "Suavidade atual: " & sm & "%"
		if c is false then return
		set c to item 1 of c
		if c starts with "Aplicar COR" then
			set f to choose folder with prompt "Escolha a pasta do evento (vídeos *_stabilized.mp4):" default location (path to desktop folder)
			do shell script "cd /tmp; /usr/bin/nohup __PYTHON__ -u " & quoted form of (basePath() & "cor.py") & " " & quoted form of (POSIX path of f) & " >>$HOME/Library/Logs/GyroflowAuto.err 2>&1 &"
		else if c starts with "Suavidade 50" then
			setSmooth(50)
			display notification "Suavidade: 50% nos próximos vídeos." with title "Gyroflow Auto"
		else
			setSmooth(30)
			display notification "Suavidade: 30% nos próximos vídeos." with title "Gyroflow Auto"
		end if
	end if
end reopen

on quit
	set rendering to do shell script "pgrep -f 'MacOS/gyroflow .*GyroflowAuto_cache' >/dev/null && echo sim || echo nao"
	if rendering is "sim" then
		set r to display dialog "Tem um vídeo sendo estabilizado agora." & return & "Se desligar, esse render é perdido (ele recomeça quando você ligar de novo e o cartão estiver plugado)." buttons {"Continuar rodando", "Desligar mesmo assim"} default button "Continuar rodando" with title "Gyroflow Auto"
		if button returned of r is "Continuar rodando" then return
	end if
	try
		do shell script "f=" & quoted form of (basePath() & "gyroflow_auto.pid") & "; [ -f \"$f\" ] && kill $(cat \"$f\") 2>/dev/null; pkill -f 'MacOS/gyroflow .*GyroflowAuto_cache' 2>/dev/null; true"
		display notification "Desligado." with title "Gyroflow Auto"
	end try
	continue quit
end quit
