// Penjaga CSP (DIG-208). nginx memasang `script-src 'self'` dan `style-src 'self'
// https://fonts.googleapis.com`, jadi skrip inline, handler on*, dan HTML mentah akan
// diblokir browser di staging walau berjalan normal di `npm run dev`. Tes ini gagal lebih
// dulu supaya masalahnya ketahuan di CI, bukan setelah deploy.
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { describe, expect, it } from 'vitest';

const root = join(__dirname, '..');
const src = join(root, 'src');

function sourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) return sourceFiles(path);
    return /\.(ts|tsx)$/.test(name) && !/\.test\.tsx?$/.test(name) ? [path] : [];
  });
}

const FORBIDDEN: [RegExp, string][] = [
  [/dangerouslySetInnerHTML/, 'dangerouslySetInnerHTML'],
  [/\.innerHTML\s*=/, 'innerHTML'],
  [/\beval\s*\(/, 'eval()'],
  [/new\s+Function\s*\(/, 'new Function()'],
  [/javascript:/i, 'URL javascript:'],
  [/<style[\s>]/, 'elemen <style>'],
];

describe('kode frontend sesuai Content-Security-Policy', () => {
  it('index.html tidak punya skrip inline atau handler on*', () => {
    const html = readFileSync(join(root, 'index.html'), 'utf8');
    const inlineScripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)].filter(
      ([, attrs, body]) => !/\bsrc=/.test(attrs) || body.trim() !== '',
    );
    expect(inlineScripts).toEqual([]);
    expect(html).not.toMatch(/\son[a-z]+\s*=/i);
  });

  it('index.html hanya memuat stylesheet dari origin sendiri atau Google Fonts', () => {
    const html = readFileSync(join(root, 'index.html'), 'utf8');
    const hrefs = [...html.matchAll(/<link\b[^>]*rel="stylesheet"[^>]*href="([^"]+)"/g)].map(
      ([, href]) => href,
    );
    for (const href of hrefs) {
      expect(href.startsWith('/') || href.startsWith('https://fonts.googleapis.com/')).toBe(true);
    }
  });

  it('kode sumber tidak memakai pola yang diblokir CSP', () => {
    const found = sourceFiles(src).flatMap((file) => {
      const text = readFileSync(file, 'utf8');
      return FORBIDDEN.filter(([pattern]) => pattern.test(text)).map(
        ([, label]) => `${relative(root, file)}: ${label}`,
      );
    });
    expect(found).toEqual([]);
  });
});
