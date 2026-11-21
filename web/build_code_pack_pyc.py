import zipfile, tempfile, os, shutil, json, subprocess

PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
CODE_ZIP = os.path.join(PROJECT_ROOT, 'ot', 'web', 'root', '_packs', '_code.zip')
PACKS_JSON = os.path.join(PROJECT_ROOT, 'ot', 'web', 'root', 'packs.json')
BACKUP_ZIP = CODE_ZIP + '.before-pyc'

if not os.path.exists(BACKUP_ZIP):
    shutil.copy2(CODE_ZIP, BACKUP_ZIP)
    print(f'Backed up original _code.zip to {BACKUP_ZIP}')

# Step 1: Unpack _code.zip into a temporary directory
work_dir = os.path.join(PROJECT_ROOT, '_tmp_code_unpack')
if os.path.exists(work_dir):
    shutil.rmtree(work_dir)
os.makedirs(work_dir)

print('Unpacking _code.zip...')
with zipfile.ZipFile(CODE_ZIP, 'r') as z:
    z.extractall(work_dir)

# The unpacked folder has _code/ as its root
code_root = os.path.join(work_dir, '_code')
print(f'Extracted to {code_root}')

# Step 2: Run compileall inside Docker Python 3.12 with UNCHECKED_HASH
print('Compiling bytecode with Python 3.12 in Docker...')
docker_cmd = [
    'docker', 'run', '--rm',
    '-v', f'{work_dir}:/work',
    'python:3.12-slim',
    'python3', '-c',
    'import compileall, py_compile; '
    'print("Running compileall..."); '
    'res = compileall.compile_dir("/work/_code", invalidation_mode=py_compile.PycInvalidationMode.UNCHECKED_HASH, force=True, optimize=0, quiet=1); '
    'print("compileall finished:", res)'
]

proc = subprocess.run(docker_cmd, capture_output=True, text=True)
print('Docker stdout:', proc.stdout)
if proc.stderr:
    print('Docker stderr:', proc.stderr)
if proc.returncode != 0:
    raise RuntimeError('Docker compilation failed!')

# Step 3: Zip everything back into _code.zip (ZIP_STORED, matching upstream make_ot_packs.py)
print('Repacking _code.zip...')
tmp_zip = CODE_ZIP + '.new'
py_count = 0
pyc_count = 0
other_count = 0

with zipfile.ZipFile(tmp_zip, 'w', zipfile.ZIP_STORED) as zout:
    for root, dirs, files in os.walk(work_dir):
        for f in files:
            full_path = os.path.join(root, f)
            rel_path = os.path.relpath(full_path, work_dir).replace('\\', '/')
            zout.write(full_path, rel_path)
            if f.endswith('.py'):
                py_count += 1
            elif f.endswith('.pyc'):
                pyc_count += 1
            else:
                other_count += 1

os.replace(tmp_zip, CODE_ZIP)
new_size = os.path.getsize(CODE_ZIP)
print(f'New _code.zip created: {new_size} bytes ({new_size/1024/1024:.1f} MB)')
print(f'  .py files: {py_count}')
print(f'  .pyc files: {pyc_count}')
print(f'  other files: {other_count}')

# Step 4: Update packs.json
with open(PACKS_JSON, 'r') as f:
    packs = json.load(f)
assert packs[0][0] == '_code'
old_size = packs[0][1]
packs[0][1] = new_size
with open(PACKS_JSON, 'w') as f:
    json.dump(packs, f)
print(f'Updated packs.json: _code size {old_size} -> {new_size}')

# Clean up work dir
shutil.rmtree(work_dir)
print('Done!')
