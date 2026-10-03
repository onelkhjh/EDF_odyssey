import sys
from tms_pc.main import main

sys.argv.append("--mock")
raise SystemExit(main())
