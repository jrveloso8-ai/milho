$TaskName = "MilhoTrader_Atualizacao_Diaria"
$BatPath = "C:\Projetos Phyton\Milho\executar_publicacao_agendada.bat"
$WorkingDir = "C:\Projetos Phyton\Milho"

Write-Host "Configurando Agendador de Tarefas do Windows..." -ForegroundColor Cyan

$Action = New-ScheduledTaskAction -Execute $BatPath -WorkingDirectory $WorkingDir
$Trigger = New-ScheduledTaskTrigger -Daily -At "07:30"
$Settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Minutes 30)

try {
    Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false -ErrorAction SilentlyContinue
    Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Description "Atualização diária automática do Milho Trader (Curva CCM, GitHub e Vercel)"
    Write-Host "`n[SUCESSO] Tarefa agendada criada com sucesso!" -ForegroundColor Green
    Write-Host "Nome: $TaskName"
    Write-Host "Horário: Todos os dias às 07:30 AM"
    Write-Host "Opção 'StartWhenAvailable': Ativa (executará assim que o PC ligar caso esteja desligado no horário)"
} catch {
    Write-Host "`n[ERRO] Falha ao registrar tarefa: $_" -ForegroundColor Red
    exit 1
}
