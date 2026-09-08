# ИНАЯ СРЕДА — 2 года

HTML-презентация юбилея клуба. Самодостаточный дек: шрифт вшит, фото и видео рядом, интернет для показа не нужен.

## Онлайн

- Тёмная тема: `/` (`index.html`)
- Светлая тема: `/light.html`

Управление: `→` / пробел — вперёд, `←` — назад, номер + `Enter` — прыжок, `F` — полный экран.

## Деплой на ONREZA

Репозиторий готов к Git-интеграции ONREZA:

| Настройка | Значение |
|---|---|
| Compute | **Static** (обязательно — не Process) |
| Build Command | `npm run build` |
| Output Directory | `dist` |
| Root Directory | `.` |
| Install Command | `npm install --ignore-scripts` |

В репозитории лежит `onreza.toml` с `deploy.compute = "static"`. Если в UI
проекта Compute всё ещё Process — переключите вручную: иначе платформа
пытается запустить браузерный JS как Bun-сервер.

После пуша в `main` и привязки репозитория в [app.onreza.ru](https://app.onreza.ru) платформа соберёт `dist/` и опубликует статику.

Локально:

```bash
npm run build
npx serve dist
```

## Структура

```
deck/           # исходник сайта (то, что уходит в dist/)
scripts/build.mjs
package.json
```

Рабочие материалы сценария (`PROMPT.md`, `scenario-clean.md`) лежат в репозитории для правок контента; в сборку не входят.
