"""Common functions.

### purpose
# custom modules used across .py scripts
###
"""

import os
import pickle
from os import path as op


def fs(directory):
    return sorted([op.join(directory, f) for f in os.listdir(directory)])


def pkldump(obj, f):
    with open(f, 'wb') as o:
        pickle.dump(obj, o, protocol=pickle.HIGHEST_PROTOCOL)


def pklload(path):
    pkl = pickle.load(open(path, 'rb'))
    return pkl


def get_email_info(parentdir, stage):
    pkl = op.join(parentdir, 'email_opts.pkl')
    if op.exists(pkl):
        email_info = pklload(pkl)
        # email_info = {'email': 'lindb@vcu.edu', 'opts': ['pipeline-finish']}  # for testing

        # make text
        email_text = '''#SBATCH --mail-user=%s''' % email_info['email']
        options = [opt.upper() for opt in email_info['opts'] if opt != 'pipeline-finish']
        # first determine if it's only when the pipeline finishes
        if email_info['opts'] == ['pipeline-finish'] and stage != 'final':
            # if default opt, but it's not the final stage
            return ''
        elif 'pipeline-finish' in email_info['opts'] and stage == 'final':
            email_text = email_text + '\n' + "#SBATCH --mail-type=END"
            if 'END' in options:
                options.remove('END')
        # now for stages earlier than final
        for opt in options:
            email_text = email_text + '\n#SBATCH --mail-type=%s' % opt
        return email_text
    else:
        # no email options
        return ''


def uni(mylist):
    return list(set(mylist))


def luni(mylist):
    return len(uni(mylist))


def makedir(directory):
    if not op.exists(directory):
        os.makedirs(directory)
    return directory


def createdirs(dirs):
    for d in dirs:
        makedir(d)


class Bcolors:
    HEADER = '\033[95m'
    OKBLUE = '\033[94m'
    OKGREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


def askforinput():
    "Ask for input; if no, exit."
    print('\n')
    while True:
        inp = input(Bcolors.WARNING + "INPUT NEEDED: Do you want to proceed? (yes | no): " + Bcolors.ENDC).lower()
        if inp in ['yes', 'no']:
            if inp == 'no':
                print('exiting %s' % sys.argv[0])
                exit()
            break
        else:
            print(Bcolors.FAIL + "Please respond with 'yes' or 'no'" + Bcolors.ENDC)
