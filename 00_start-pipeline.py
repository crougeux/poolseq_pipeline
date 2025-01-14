"""
start the pipeline.

### usage
# 00_start-pipeline.py -p PARENTDIR [-e EMAIL [-n EMAIL_OPTIONS]]
###

### assumes
# that samples duplicated in the 'sample_name' column have the same rglb, rgsm, and rgpl read groups
# that ploidy is the same across samples in a pool
###
"""

import os, sys, distutils.spawn, subprocess, shutil, argparse, create_bedfiles, pandas as pd
import balance_queue
from os import path as op
from collections import OrderedDict
from coadaptree import fs, pkldump, uni, luni, makedir, askforinput, Bcolors


def create_sh(pooldirs, poolref):
    """
run 01_trim-fastq.py to sbatch trimming jobs, then balance queue.

Positional arguments:
pooldirs - a list of subdirectories in parentdir for groups of pools
poolref - dictionary with key = pool, val = /path/to/ref
    """
    # create sh files
    print(Bcolors.BOLD + '\nwriting sh files' + Bcolors.ENDC)
    for pooldir in pooldirs:
        pool = op.basename(pooldir)
        print(Bcolors.BOLD + '\npool = %s' % pool + Bcolors.ENDC)
        ref = poolref[pool]
        print('\tsending pooldir and ref to 01_trim-fastq.py')
        subprocess.call([shutil.which('python'),
                         op.join(os.environ['HOME'], 'pipeline/01_trim-fastq.py'),
                         pooldir,
                         ref])
    print("\n")
    balance_queue.main('balance_queue.py', 'trim')


def get_datafiles(parentdir, f2pool, data):
    """Get list of files from datatable, make sure they exist in parentdir.
    Create symlinks in /parentdir/<pool_name>/.

    Positional arguments:
    parentdir - directory with datatable.txt and (symlinks to) fastq data
    f2pool - dictionary with key = file.fastq, val = pool_name
    data - datatable.txt with info for pipeline
    """
    print(Bcolors.BOLD + '\nchecking for existance of fastq files in datatable.txt' + Bcolors.ENDC)
    files = [f for f in fs(parentdir) if 'fastq' in f and 'md5' not in f]
    datafiles = data['file_name_r1'].tolist()
    for x in data['file_name_r2'].tolist():
        datafiles.append(x)
    if len(files) > len(datafiles):
        desc = 'more'
    if len(files) < len(datafiles):
        desc = 'less'
    try:
        print(Bcolors.WARNING +
              'WARN: there are %s fastq files in %s than in datatable.txt' % (desc, parentdir) +
              Bcolors.ENDC)
        print(Bcolors.BOLD + 'Here are the files in %s' % parentdir + Bcolors.ENDC)
        [print(op.basename(x)) for x in files]
        print(Bcolors.BOLD + 'Here are the files in datatable.txt' + Bcolors.ENDC)
        [print(x) for x in datafiles]
        askforinput()

    except NameError:
        pass

    for f in datafiles:
        src = op.join(parentdir, f)
        if not op.exists(src):
            # make sure file in datatable exists
            print("could not find %s in %s\nmake sure file_name in datatable is its basename" % (f, parentdir))
            print("(symlinks in parentdir to fastq files in other dirs works fine, and is the intentional use)")
            sys.exit(1)
        pooldir = op.join(parentdir, f2pool[f])
        dst = op.join(pooldir, f)
        if not op.exists(dst):
            # easy to visualize in cmdline if script is finding correct group of files by ls-ing pooldir
            os.symlink(src, dst)


def make_pooldirs(data, parentdir):
    """Create subdirectories of parentdir.

    Positional arguments:
    data - datatable.txt with info for pipeline
    parentdir - directory with datatable.txt and (symlinks to) fastq data
    """
    # make pool dirs
    print(Bcolors.BOLD + "\nmaking pool dirs" + Bcolors.ENDC)
    pools = uni(data['pool_name'].tolist())
    pooldirs = []
    for p in pools:
        DIR = op.join(parentdir, p)
        if op.exists(DIR):
            print("The pooldir already exists, this could overwrite previous data: %s" % DIR)
            print("Do you want to proceed?")
            askforinput()
        pooldirs.append(makedir(DIR))
    return pooldirs


def create_all_bedfiles(poolref):
    """For each unique ref.fa in datatable.txt, create bedfiles for varscan/crisp.

    Positional arguments:
    poolref - dictionary with key = pool, val = /path/to/ref
    """
    # create bedfiles for crisp and varscan
    print(Bcolors.BOLD + "\ncreating bedfiles" + Bcolors.ENDC)
    for ref in uni(poolref.values()):
        create_bedfiles.main(ref)


def read_datatable(parentdir):
    """Read in datatable.txt"""
    # read in the datatable, save rginfo for later
    datatable = op.join(parentdir, 'datatable.txt')
    if not op.exists(datatable):
        print(Bcolors.FAIL + '''FAIL: the datatable is not in the necessary path: %s
FAIL: exiting 00_start-pipeline.py''' % datatable + Bcolors.ENDC)
        sys.exit(3)
    print(Bcolors.BOLD + 'reading datatable, getting fastq info' + Bcolors.ENDC)
    data = pd.read_csv(datatable, sep='\t')
    rginfo = {}     # key=samp vals=rginfo
    samp2pool = {}  # key=samp val=pool
    poolref = {}    # key=pool val=ref.fa
    ploidy = {}     # key=pool val=ploidy
    poolsamps = {}  # key=pool val=sampnames
    f2samp = {}     # key=f val=samp
    f2pool = {}     # key=f val=pool
    adaptors = OrderedDict()  # key=samp val={'r1','r2'} val=adaptor
    for row in data.index:
        samp = data.loc[row, 'sample_name']
        adaptors[samp] = {'r1': data.loc[row, 'adaptor_1'],
                          'r2': data.loc[row, 'adaptor_2']}
        pool = data.loc[row, 'pool_name']
        pooldir = op.join(parentdir, pool)
        print('\t{}\tsamp = {}\tpool = {}'.format(row, samp, pool))
        if pool not in poolsamps:
            poolsamps[pool] = []
        if samp not in poolsamps[pool]:
            poolsamps[pool].append(samp)
        if samp in samp2pool:
            if samp2pool[samp] != pool:
                print(Bcolors.FAIL + 'FAIL: there are duplicate sample names with \
different pool assignments: %s' % samp + Bcolors.ENDC)
                print('exiting')
                exit()
        samp2pool[samp] = pool
        df = data[data['pool_name'] == pool].copy()
        if not luni(df['ploidy']) == 1:
            print("the ploidy values for some elements with pool name '%s' are not the same" % pool)
            sys.exit(1)
        if pool not in ploidy:
            ploidy[pool] = data.loc[row, 'ploidy']
        if pool in poolref:
            if not poolref[pool] == data.loc[row, 'ref']:
                print("ref genome for samples in %s pool seems to have different paths in datatable.txt" % pool)
                sys.exit(1)
        else:
            ref = data.loc[row, 'ref']
            if not op.exists(ref):
                print('ref for %s does not exist in path: %s' % (samp, ref))
                print('exiting %s' % '00_start-pipeline.py')
                exit()
            needed = []
            for suffix in ['.dict', '.amb', '.ann', '.bwt', '.fai', '.pac', '.sa']:
                refext = ref + suffix if suffix != '.dict' else ref.split('.fa')[0] + suffix
                if not op.exists(refext):
                    needed.append(refext)
            if len(needed) > 0:
                print(Bcolors.FAIL +
                      'FAIL: the following extensions of the reference are needed to continue, \
please create these files' +
                      Bcolors.ENDC)
                for n in needed:
                    print(Bcolors.FAIL + n + Bcolors.ENDC)
                print('exiting')
                exit()
            poolref[pool] = ref
        rginfo[samp] = {}
        for col in ['rglb', 'rgpl', 'rgsm']:  # rg info columns
            rginfo[samp][col] = data.loc[row, col]
        for f in [data.loc[row, 'file_name_r1'], data.loc[row, 'file_name_r2']]:
            f2pool[f] = pool
            f2samp[op.join(pooldir, f)] = samp
    pkldump(rginfo, op.join(parentdir, 'rginfo.pkl'))
    pkldump(ploidy, op.join(parentdir, 'ploidy.pkl'))
    pkldump(f2samp, op.join(parentdir, 'f2samp.pkl'))
    pkldump(poolsamps, op.join(parentdir, 'poolsamps.pkl'))
    pkldump(poolref, op.join(parentdir, 'poolref.pkl'))
    pkldump(adaptors, op.join(parentdir, 'adaptors.pkl'))
    pkldump(samp2pool, op.join(parentdir, 'samp2pool.pkl'))
    return data, f2pool, poolref


def check_reqs():
    """Check for assumed exports."""
    print(Bcolors.BOLD + '\nchecking for exported variables' + Bcolors.ENDC)
    for var in ['SLURM_ACCOUNT', 'SBATCH_ACCOUNT', 'SALLOC_ACCOUNT',
                'CRISP_DIR', 'VARSCAN_DIR', 'PYTHONPATH', 'SQUEUE_FORMAT']:
        try:
            print('\t%s = %s' % (var, os.environ[var]))
        except KeyError:
            print('\tcould not find %s in exported vars\n\texport this var in $HOME/.bashrc so it can be used \
later in pipeline\n\texiting 00_start-pipeline.py' % var)
            exit()
    for program in [op.join(os.environ['VARSCAN_DIR'], 'VarScan.v2.4.3.jar'),
                    op.join(os.environ['CRISP_DIR'], 'CRISP')]:
        if not op.exists(program):
            print(Bcolors.BOLD +
                  Bcolors.FAIL +
                  "FAIL: could not find the following program: %s" % program +
                  Bcolors.ENDC)
    # make sure an environment can be activated (activation assumed to be in $HOME/.bashrc)
    for exe in ['activate']:
        if distutils.spawn.find_executable(exe) is None:
            print('\tcould not find %s in $PATH\nexiting 00_start-pipeline.py' % exe)
            if exe == 'activate':
                print('\t\t(the lack of activate means that the python env is not correctly installed)')
            exit()
    # make sure pipeline can be accessed via $HOME/pipeline
    if not op.exists(op.join(os.environ['HOME'], 'pipeline')):
        print('\tcould not find pipeline via $HOME/pipeline')
        exit()


def check_pyversion():
    """Make sure python version is 3.6+"""
    pyversion = float(str(sys.version_info[0]) + '.' + str(sys.version_info[1]))
    if not pyversion >= 3.6:
        text = '''FAIL: You are using python %s. This pipeline was built with python 3.7+.
FAIL: You will need at least python v3.6+.
FAIL: exiting 00_start-pipeline.py
    ''' % pyversion
        print(Bcolors.BOLD + Bcolors.FAIL + text + Bcolors.ENDC)
        exit()


def get_pars():
    choices = ['all', 'fail', 'begin', 'end', 'pipeline-finish']
    parser = argparse.ArgumentParser(description=print(mytext),
                                     add_help=False,
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    requiredNAMED = parser.add_argument_group('required arguments')
    requiredNAMED.add_argument("-p",
                               required=True,
                               default=argparse.SUPPRESS,
                               dest="parentdir",
                               type=str,
                               help="/path/to/directory/with/fastq.gz-files/")
    parser.add_argument("-e",
                        required=False,
                        dest="email",
                        help="the email address you would like to have notifications sent to")
    parser.add_argument("-n",
                        default=argparse.SUPPRESS,
                        nargs='+',
                        required=False,
                        dest="email_options",
                        help='''the type(s) of email notifications you would like to receive from the pipeline.\
                        Requires --email-address. These options are used to fill out the #SBATCH flags.
must be one (or multiple) of %s''' % [x for x in choices])
    parser.add_argument('-h', '--help',
                        action='help',
                        default=argparse.SUPPRESS,
                        help='Show this help message and exit.\n')
    args = parser.parse_args()
    if args.parentdir.endswith('/'):
        args.parentdir = args.parentdir[:-1]
    if args.email and args.email_options is None:
        print(Bcolors.FAIL + 'FAIL: --notification-types are required when specifying email' + Bcolors.ENDC)
        print(Bcolors.FAIL + 'FAIL: choices = {%s}\n' % [x for x in choices] + Bcolors.ENDC)
        exit()
    if args.email_options and args.email is None:
        print(Bcolors.FAIL + 'FAIL: specifying --notification-types requires specifying \
--email-address\n' + Bcolors.ENDC)
        exit()
    if args.email_options:
        for choice in args.email_options:
            if not choice.lower() in choices:
                print(Bcolors.FAIL +
                      '''FAIL: There can be multiple options, but they must be from the set:''' +
                      Bcolors.ENDC)
                print(Bcolors.FAIL +
                      '''\t%s\n''' % choices +
                      Bcolors.ENDC)
                exit()
    if args.email:
        if '@' not in args.email:
            print(Bcolors.FAIL + 'FAIL: email address does not have an "@" symbol in it, \
please check input\n' + Bcolors.ENDC)
            exit()
        if 'all' in args.email_options:
            args.email_options = ['all']
        # save email
        epkl = {'email': args.email,
                'opts': args.email_options}
        pkldump(epkl, op.join(args.parentdir, 'email_opts.pkl'))

    return args


def main():
    # parse arguments
    args = get_pars()

    # WARN if version = 3.6, FAIL if < 3.6
    check_pyversion()

    # look for exported vars (should be in .bashrc)
    check_reqs()

    # read in the datatable
    data, f2pool, poolref = read_datatable(args.parentdir)

    # create bedfiles to parallelize crisp and varscan later on
    create_all_bedfiles(poolref)

    # create directories for each group of pools to be combined
    pooldirs = make_pooldirs(data, args.parentdir)

    # assign fq files to pooldirs for visualization (good to double check)
    get_datafiles(args.parentdir, f2pool, data)

    # create and sbatch sh files
    create_sh(pooldirs, poolref)


if __name__ == '__main__':
    mytext = Bcolors.BOLD + Bcolors.OKGREEN + '''
*****************************************************************************


         ___|               \         |          _   __|
        |      _ \           \    __  |  _     _    |    _|  _ \\  _ \\
        |     (   | __|   /_  \  (    | (   | (  |  |   |    __/  __/
         ___|\___/      _/    _\\\___/_|\__/_|  __/  |  _|  \___|\___|
                                              |
                                              |

                         VarScan and CRISP pipeline

*****************************************************************************


''' + Bcolors.ENDC

    main()
