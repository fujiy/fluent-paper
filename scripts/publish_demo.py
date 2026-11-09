"""Publish the selected public demo as a normal, non-force gh-pages commit."""
from pathlib import Path
import shutil,subprocess,tempfile
source=Path(__file__).resolve().parents[1]/'demo'
assert (source/'ATTRIBUTION.txt').is_file() and (source/'index.html').is_file()
with tempfile.TemporaryDirectory(prefix='fluent-public-pages-') as temporary:
 destination=Path(temporary)
 subprocess.run(['git','clone','--quiet','--single-branch','--branch','gh-pages','git@github.com:fujiy/fluent-paper.git',str(destination)],check=True)
 for path in destination.iterdir():
  if path.name=='.git':continue
  if path.is_dir():shutil.rmtree(path)
  else:path.unlink()
 shutil.copytree(source,destination,dirs_exist_ok=True)
 def git(*args):return subprocess.run(['git',*args],cwd=destination,check=True)
 git('add','.')
 if subprocess.run(['git','diff','--cached','--quiet'],cwd=destination).returncode==0:
  print('Public sample is unchanged.')
 else:
  git('commit','-m','Update licensed PDF reader sample');git('push','origin','gh-pages')
