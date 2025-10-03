@echo off
echo Liberando a porta 5000 no Firewall do Windows...
netsh advfirewall firewall add rule name="Flask Porta 5000" dir=in action=allow protocol=TCP localport=5000
echo Porta 5000 liberada com sucesso!
pause
