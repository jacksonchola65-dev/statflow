import sys, traceback
sys.path.insert(0, r"c:\Users\LION CULTURE\Desktop\statflow\backend")
try:
    import importlib
    m = importlib.import_module('app.main')
    print('IMPORT_OK')
except Exception as e:
    traceback.print_exc()
    print('IMPORT_ERROR', e)
