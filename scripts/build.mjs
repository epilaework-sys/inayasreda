#!/usr/bin/env node
/**
 * Статическая сборка для ONREZA: копирует готовый дек в dist/.
 * Сборки фронтенд-бандлера нет — HTML/CSS/JS уже самодостаточны.
 */
import { cpSync, mkdirSync, rmSync, existsSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';

const root = process.cwd();
const src = join(root, 'deck');
const out = join(root, 'dist');

if (!existsSync(src)) {
  console.error('Нет папки deck/ — нечего собирать');
  process.exit(1);
}

rmSync(out, { recursive: true, force: true });
mkdirSync(out, { recursive: true });
cpSync(src, out, { recursive: true });

// Якорь для платформы: корень сайта — тёмная тема; светлая — /light.html
writeFileSync(
  join(out, '_headers'),
  `/*
  Cache-Control: public, max-age=3600
/video/*
  Cache-Control: public, max-age=86400
/img/*
  Cache-Control: public, max-age=86400
`
);

console.log('dist/ готов — статический HTML-дек');
