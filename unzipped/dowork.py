import subprocess
import urllib

print('<?xml version="1.0" encoding="utf-8"?><items>')

cmdout = subprocess.check_output('Rscript -e "{query}"')
lines = cmdout.split('\n')
for line in lines:
    print('<item valid="yes"><title>')
    print(urllib.quote(line))
    print('</title></item>')

print('</items>')
