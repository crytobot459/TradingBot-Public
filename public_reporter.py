import ast
import os
import shutil
import subprocess
import argparse
import json
import re
from pathlib import Path
from typing import List
GITHUB_REPO_URL = 'https://github.com/YourUsername/YourRepoName.git'
PUBLIC_DIR_NAME = 'TradingBot-Public'
ENABLE_TRANSLATION = True
TARGET_LANGUAGE = 'en'
FILES_TO_OBSCURE = {'ichimoku_scanner.py': ['analyze_and_score', 'calculate_trade_parameters', 'calculate_success_probability', 'analyze_market_context', '_synthesize_market_extremes', '_evaluate_market_factors', 'find_triple_bottom_pattern', 'find_double_bottom_pattern', 'detect_kumo_twist', 'assess_short_term_health', 'score_long_term_squeeze', 'score_trending_pullback_setup', 'analyze_breakout_structure', 'generate_plan_for_unmanaged_trade', '_assess_reversal_context', '_apply_reversal_safety_filter', 'find_bullish_divergence', 'find_bearish_divergence', '_measure_downward_momentum'], 'automation_manager.py': ['analyze_market_state', 'manage_open_trade_plan', 'get_bot_instructions'], 'external_signal_strategy.py': ['populate_entry_trend', 'populate_exit_trend', 'custom_stoploss', 'custom_exit', '_calculate_bullish_divergence_v3', '_get_trade_health_check_v2']}
EXCLUDE_PATTERNS = ['__pycache__', '.git', '.vscode', '.idea', '*.pyc', '*.bak', '*.log', '*.sqlite', 'user_data', 'venv', 'env', PUBLIC_DIR_NAME, os.path.basename(__file__)]
SENSITIVE_CONFIG_MAP = {'config.json': 'config.example.json', 'telegram_data.json': None, 'trades.json': None}
OBSCURED_DOCSTRING = '\n[PROPRIETARY LOGIC HIDDEN]\n---------------------------------------------------------\nThis function contains advanced algorithmic logic for:\n- Pattern Recognition & Signal Processing\n- Dynamic Risk Management (DEFCON System)\n- Automated Trade Execution\n\nThe implementation details and specific parameters have been\nremoved to protect Intellectual Property (IP).\n---------------------------------------------------------\n'
try:
    from deep_translator import GoogleTranslator
except ImportError:
    print("Error: 'deep-translator' library not found. Please run 'pip install deep-translator'")
    GoogleTranslator = None

def translate_text_block(text, target_lang):
    """Translates a block of text, handling potential errors."""
    if not GoogleTranslator or not text or (not text.strip()):
        return text
    try:
        return GoogleTranslator(source='auto', target=target_lang).translate(text)
    except Exception as e:
        print(f'    ⚠️ Translation failed: {e}. Using original text.')
        return text

class CodeTranslator(ast.NodeTransformer):
    """
    AST transformer to translate docstrings within Python code.
    This is safer than regex for multi-line docstrings.
    """

    def __init__(self, target_lang):
        self.target_lang = target_lang

    def visit_FunctionDef(self, node):
        docstring = ast.get_docstring(node)
        if docstring:
            translated_docstring = translate_text_block(docstring, self.target_lang)
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                node.body[0].value.s = translated_docstring
        self.generic_visit(node)
        return node

    def visit_Module(self, node):
        docstring = ast.get_docstring(node)
        if docstring:
            translated_docstring = translate_text_block(docstring, self.target_lang)
            if node.body and isinstance(node.body[0], ast.Expr) and isinstance(node.body[0].value, ast.Constant):
                node.body[0].value.s = translated_docstring
        self.generic_visit(node)
        return node

def translate_comments_in_file(filepath: Path, target_lang: str):
    """Translates single-line comments (  # ) line by line."""
    if not GoogleTranslator:
        return
    content = filepath.read_text(encoding='utf-8').splitlines()
    translated_content = []
    for line in content:
        match = re.match('^(\\s*)(.*?)\\s*(  # \\s*(.*))$', line)
        if match:
            indent, code_part, full_comment, comment_text = match.groups()
            if comment_text:
                translated_comment = translate_text_block(comment_text, target_lang)
                new_line = f'{indent}{code_part.rstrip()}  # {translated_comment}'
                translated_content.append(new_line)
            else:
                translated_content.append(line)
        else:
            translated_content.append(line)
    filepath.write_text('\n'.join(translated_content), encoding='utf-8')

def process_python_file(filepath: Path, functions_to_hide: List[str], translate: bool, lang: str):
    """Reads a file, applies transformations (obscuring, translation), and writes it back."""
    try:
        source_code = filepath.read_text(encoding='utf-8')
        tree = ast.parse(source_code)
        if functions_to_hide:

            class FunctionObscurer(ast.NodeTransformer):

                def visit_FunctionDef(self, node):
                    if node.name in functions_to_hide:
                        node.args.args, node.args.defaults, node.args.kw_defaults, node.args.kwonlyargs = ([], [], [], [])
                        node.args.vararg = ast.arg(arg='args')
                        node.args.kwarg = ast.arg(arg='kwargs')
                        node.returns = None
                        original_docstring = ast.get_docstring(node)
                        new_body = [ast.Expr(value=ast.Constant(value=OBSCURED_DOCSTRING.strip()))]
                        if original_docstring:
                            new_body.insert(0, ast.Expr(value=ast.Constant(value=original_docstring)))
                        new_body.append(ast.Pass())
                        node.body = new_body
                    return node
            tree = FunctionObscurer().visit(tree)
        if translate:
            translator = CodeTranslator(lang)
            tree = translator.visit(tree)
        ast.fix_missing_locations(tree)
        new_code = ast.unparse(tree)
        filepath.write_text(new_code, encoding='utf-8')
        if translate:
            translate_comments_in_file(filepath, lang)
    except Exception as e:
        print(f'    ❌ [CODE PROCESSING ERROR] {filepath.name}: {e}')

def create_dummy_config(dest_path: Path):
    """Creates a safe, dummy config file."""
    dummy_data = {'user_data_dir': 'user_data', 'exchange': {'name': 'binance', 'key': 'YOUR_API_KEY_HERE', 'secret': 'YOUR_SECRET_KEY_HERE', 'pair_whitelist': []}, 'telegram': {'enabled': True, 'token': 'YOUR_TELEGRAM_BOT_TOKEN', 'chat_id': 'YOUR_CHAT_ID'}, 'api_server': {'enabled': True, 'listen_ip_address': '127.0.0.1', 'listen_port': 8080, 'username': 'freqtrader', 'password': 'SuperSecurePassword'}, 'translation': {'enabled': True, 'target_language': 'en'}, 'note': 'This is a sanitized configuration template for demonstration purposes.'}
    try:
        with open(dest_path, 'w', encoding='utf-8') as f:
            json.dump(dummy_data, f, indent=4)
        print(f'    🛡️ Created dummy config: {dest_path.name}')
    except Exception as e:
        print(f'    ❌ Error creating config: {e}')

def run_git_commands(public_dir: Path, repo_url: str):
    """Automates Git: init, commit, and push if URL is provided."""
    print('\n[*] Running Git Automation...')
    try:
        subprocess.run(['git', '--version'], check=True, capture_output=True)
        subprocess.run(['git', 'init'], cwd=public_dir, check=True, capture_output=True)
        subprocess.run(['git', 'add', '.'], cwd=public_dir, check=True, capture_output=True)
        commit_msg = 'Portfolio Release: Advanced Algo Trading System (Obscured & Translated)'
        subprocess.run(['git', 'commit', '-m', commit_msg], cwd=public_dir, check=True, capture_output=True)
        print('    ✅ Git Commit successful.')
        if repo_url and 'YourUsername' not in repo_url:
            print(f'    🚀 Pushing code to: {repo_url}')
            subprocess.run(['git', 'branch', '-M', 'main'], cwd=public_dir, check=True, capture_output=True)
            subprocess.run(['git', 'remote', 'add', 'origin', repo_url], cwd=public_dir, check=False, capture_output=True)
            subprocess.run(['git', 'remote', 'set-url', 'origin', repo_url], cwd=public_dir, check=True, capture_output=True)
            subprocess.run(['git', 'push', '-u', 'origin', 'main', '--force'], cwd=public_dir, check=True, capture_output=True)
            print('    🎉 SUCCESSFULLY PUSHED TO GITHUB!')
        elif 'YourUsername' in repo_url:
            print('    ⚠️ GitHub URL has not been changed. Please update the GITHUB_REPO_URL variable in the script.')
        else:
            print('    ℹ️ Local repo created. GitHub URL not configured for automatic push.')
    except subprocess.CalledProcessError as e:
        print(f'    ❌ Git Error: {e.stderr.decode().strip()}')
    except FileNotFoundError:
        print('    ❌ Git is not installed. Please install Git to use this feature.')

def main():
    parser = argparse.ArgumentParser(description='Create a public, obscured, and translated portfolio version of the trading bot.')
    parser.add_argument('-f', '--force', action='store_true', help='Delete the old public directory without asking.')
    args = parser.parse_args()
    source_dir = Path.cwd()
    public_dir = source_dir / PUBLIC_DIR_NAME
    print(f'\n{'=' * 60}\n   PORTFOLIO CREATION & TRANSLATION PROCESS (PUBLIC VERSION)\n{'=' * 60}')
    if public_dir.exists():
        if not args.force:
            if input(f"⚠️ Directory '{PUBLIC_DIR_NAME}' already exists. Delete and recreate? (y/n): ").lower() != 'y':
                print('Operation cancelled.')
                return
        shutil.rmtree(public_dir)
    public_dir.mkdir()
    print('\n[*] Copying and filtering files...')
    count = 0
    for item in source_dir.iterdir():
        if item.name in SENSITIVE_CONFIG_MAP or any((item.match(p) for p in EXCLUDE_PATTERNS)) or item.name in EXCLUDE_PATTERNS:
            continue
        dest = public_dir / item.name
        if item.is_dir():
            shutil.copytree(item, dest)
        else:
            shutil.copy2(item, dest)
        print(f'    + {item.name}')
        count += 1
    print(f'    -> Copied {count} files/folders.')
    print('\n[*] Creating sanitized configuration file...')
    for new_name in SENSITIVE_CONFIG_MAP.values():
        if new_name:
            create_dummy_config(public_dir / new_name)
    print('\n[*] Processing Python files (Obscuring & Translating)...')
    for filename in os.listdir(public_dir):
        if filename.endswith('.py'):
            fpath = public_dir / filename
            functions_to_hide = FILES_TO_OBSCURE.get(filename, [])
            print(f'    Processing: {filename} {('(Translating)' if ENABLE_TRANSLATION else '')} {('(Obscuring)' if functions_to_hide else '')}')
            process_python_file(fpath, functions_to_hide, ENABLE_TRANSLATION, TARGET_LANGUAGE)
    run_git_commands(public_dir, GITHUB_REPO_URL)
    print(f'\n✅ PROCESS COMPLETE!')
    print(f'📁 Your safe, public code is located in: {public_dir}')
    if GITHUB_REPO_URL and 'YourUsername' not in GITHUB_REPO_URL:
        print(f'✅ Code has been automatically pushed to the repo: {GITHUB_REPO_URL.split('@')[-1]}')
    else:
        print('👉 GitHub URL not configured. You can push the contents of the public directory manually.')
if __name__ == '__main__':
    main()