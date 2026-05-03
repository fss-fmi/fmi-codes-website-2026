const fs = require('fs');
const path = require('path');

const ruffWin = './.venv/Scripts/ruff.exe';
const ruffUnix = './.venv/bin/ruff';
const ruff = fs.existsSync(path.resolve(ruffWin))
  ? ruffWin
  : fs.existsSync(path.resolve(ruffUnix))
    ? ruffUnix
    : 'python -m ruff';

module.exports = {
  '*.{html,js,json,css,md}': ['prettier --write'],
  'frontend/**/*.{ts,tsx}': [
    'node ./frontend/node_modules/eslint/bin/eslint.js --fix --config frontend/eslint.config.js',
    'prettier --write',
  ],
  '*.py': [`${ruff} check --fix`, `${ruff} format`],
};
