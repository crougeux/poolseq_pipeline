"""Create and sbatch picard and samtools command files.

### purpose
# use picard to mark/remove duplicates, build bam index for GATK
###

### usage
# 03_mark_build.py /path/to/sortfile /path/to/pooldir/
###
"""

import sys, os, balance_queue, subprocess, shutil
from os import path as op
from coadaptree import makedir, get_email_info, pklload

thisfile, pooldir, samp = sys.argv
sortfiles = pklload(op.join(pooldir, '%s_sortfiles.pkl' % samp))

# MarkDuplicates
dupdir = op.join(pooldir, '03_dedup_rg_filtered_indexed_sorted_bamfiles')
pool = op.basename(pooldir)
dupfile = op.join(dupdir, "%s_rd.bam" % samp)
dupflag = dupfile.replace(".bam", ".bam.flagstats")
dupstat = op.join(dupdir, "%s_rd_dupstat.txt" % samp)

# create sh file
email_text = get_email_info(op.dirname(pooldir), '03')
text = f'''#!/bin/bash
#SBATCH --time=11:59:00
#SBATCH --mem=30000M
#SBATCH --ntasks=1
#SBATCH --job-name={pool}-{samp}-mark
#SBATCH --output={pool}-{samp}-mark_%j.out 
{email_text}

# remove dups
module load picard/2.18.9
module load java
export _JAVA_OPTIONS="-Xms256m -Xmx27g"
java -Djava.io.tmpdir=$SLURM_TMPDIR -jar $EBROOTPICARD/picard.jar MarkDuplicates \
I={" I=".join(sortfiles)} O={dupfile} MAX_FILE_HANDLES_FOR_READ_ENDS_MAP=1000 \
M={dupstat} REMOVE_DUPLICATES=true

# Build bam index for GATK
java -jar $EBROOTPICARD/picard.jar BuildBamIndex I={dupfile}
module unload picard

# get more dup stats
module load samtools/1.9
samtools flagstat {dupfile} > {dupflag}
module unload samtools

# call next step
source $HOME/.bashrc
export PYTHONPATH="${{PYTHONPATH}}:$HOME/pipeline"
export SQUEUE_FORMAT="%.8i %.8u %.12a %.68j %.3t %16S %.10L %.5D %.4C %.6b %.7m %N (%r)"

python $HOME/pipeline/04_realignTargetCreator.py {pooldir} {samp} {dupfile}

'''

# create shdir and file
shdir = op.join(pooldir, 'shfiles/03_mark_build_shfiles')
for d in [shdir, dupdir]:
    makedir(d)
file = op.join(shdir, '%(pool)s-%(samp)s-mark.sh' % locals())
with open(file, 'w') as o:
    o.write("%s" % text)

# sbatch file
os.chdir(shdir)
print('shdir = ', shdir)
subprocess.call([shutil.which('sbatch'), file])

# balance queue
balance_queue.main('balance_queue.py', 'mark')
balance_queue.main('balance_queue.py', 'bwa')
