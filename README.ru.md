[english](README.md) · русский

# mgebot duel

локальная тренировка в TF2 от avxgroup. ставишь, выбираешь бота, играешь.

## как запустить

1. распакуй весь архив. на windows открой `mgebot-duel.exe`, на linux — `./mgebot-duel`.
2. нажми **install**. карта и плагин уже внутри, SourceMod и MetaMod скачаются сами.
3. выбери арену и нажми **start**.
4. настрой бота во вкладке **bots** и нажми **apply**. пресеты можно сохранять и кидать друзьям.

если локальная игра уже открыта с `-insecure`, приложение подключится к ней.
для обычных защищённых серверов перезапусти TF2 без `-insecure`.

## что умеет

- класс, сложность, точность, оружие и движение бота.
- точность через **auto** или обычный ползунок с процентом. уклонения и полёт снаряда всё ещё влияют на попадания.
- живой счёт, хп, урон, текущий план бота и обновления обучения.
- история дуэлей, винрейт и урон за минуту.
- общее обучение ботов на твоём компьютере. никуда ничего не отправляется.

linux: нативная TF2, x86_64, glibc 2.28+. для Proton бери windows-пакет.

## где файлы

пресеты: `%LOCALAPPDATA%/mgebot-duel` на windows, `~/.local/share/mgebot-duel` на linux (или `XDG_DATA_HOME`).

история и обучение: `tf/addons/sourcemod/data/sqlite/`.
разметка арен: `tf/addons/sourcemod/configs/botduel_editor/`.
обновление их сохраняет. не публикуй `connection.json` и `mgebot_companion.cfg`: там данные локального подключения.

## журнал сбоев

настройки → **журнал сбоев TF2**. файлы лежат в `crashlogs/` внутри папки данных приложения.
хранятся последние 10 отчётов: код выхода, долгие зависания, конец консоли, ошибки SourceMod и доступные дампы TF2.
запись работает до выхода из TF2, даже если закрыть приложение. ничего не отправляется в сеть.

## исходники и сборка

нужен Python 3.12+. поставь `requirements.txt` и запусти `python run.py`.
для запуска из исходников передай пакет плагина через `--payload путь/к/пакету.zip`. в готовом приложении он уже есть.

```sh
python scripts/build.py --platform windows --out build/windows --cache build/cache --payload mgebot_duel_5.1.2_Windows_x64.zip
python scripts/build.py --platform linux --out build/linux --cache build/cache --payload mgebot_duel_5.1.2_Linux_x64.zip
python scripts/package.py --out dist --build build/windows --build build/linux
```

для сборки windows нужен MinGW-w64, для linux — `dpkg-deb`. Python и Qt попадут в готовый архив.
закрытого кода SourcePawn в исходниках приложения нет.

[изменения](CHANGELOG.ru.md) · [лицензия](LICENSE) · [авторы и зависимости](THIRD_PARTY.md)
