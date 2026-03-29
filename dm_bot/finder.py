import requests

import os


filenames = os.listdir("x")

filenames = [f[5:] for f in filenames]

cdns = ["cdn0{}".format(str(i).zfill(2)) for i in range(1, 20)]
ocdns = ["o{}".format(s) for s in cdns]

cdns = cdns + ocdns
