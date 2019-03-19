### fix
# uncomment exit() in checksq()
###

###
# usage: balance_queue.py phaseOFpipeline
###

###
# purpose: evenly redistributes jobs across available accounts based on priority based on the job name (phaseOFpipeline);
#          helps speed up effective run time
###

import os, shutil, sys, math, subprocess


def announceacctlens(accounts, fin):
    print('%s job announcement' % ('final' if fin is True else 'first'))
    for account in accounts:
        print('%s jobs on %s' % (str(len(accounts[account])), account))


def checksq(sq):
    exitneeded = False
    if not isinstance(sq, list):
        print("type(sq) != list, exiting %(thisfile)s" % globals())
        exitneeded = True
    if len(sq) == 0:
        print("len(sq) == 0, exiting %(thisfile)s" % globals())
        exitneeded = True
    for s in sq:
        if not s == '':
            if 'socket' in s.lower():
                print("socket in sq return, exiting %(thisfile)s" % globals())
                exitneeded = True
            try:
                assert int(s.split()[0]) == float(s.split()[0])
            except AssertionError:
                print("could not assert int == float, %s" % (s[0]))
                exitneeded = True
    if exitneeded == True:
        print('slurm screwed something up for %(thisfile)s %(phase)s, lame' % globals())
        exit()
    else:
        return sq


def getsq(grepping):
    # TODO: if I import getsq(), I might not want to exit if slurm screwed something up
    if not __name__ == '__main__':
        # so I don't have to worry about remembering to import both functions
        from balance_queue import checksq
    if isinstance(grepping, str):
        # in case I pass a single str instead of a list of strings
        grepping = [grepping]

    # get the pending queue, without a header
    # sq = os.popen('''squeue -u %(user)s -t "PD" | grep %(phase)s | grep Priority''' % locals()).read().split("\n")
    # sq = subprocess.Popen([shutil.which('squeue'), '-u', os.environ['USER'], '-h', '-t', 'PD'],
    #                       stdout=subprocess.PIPE,
    #                       universal_newlines=True).communicate()[0].split("\n")
    sq = subprocess.check_output([shutil.which('squeue'),
                                  '-u',
                                  os.environ['USER'],
                                  '-h',]).decode('utf-8').split('\n')
    sq = [s for s in sq if not s == '']

    # look for the things I want to grep (serial subprocess.Popen() are a pain with grep)
    grepped = []
    if len(sq) > 0:
        for grep in grepping:
            for q in sq:
                splits = q.split()
                if not 'CG' in splits(): # grep -v 'CG'
                    for split in splits:
                        if grep.lower() in split.lower():
                            grepped.append(tuple(splits))
        if len(grepped) > 0:
            return checksq(sq)
    else:
        print('no jobs in queue to balance')
        exit()


def adjustjob(acct, jobid):
    subprocess.Popen([shutil.which('scontrol'), 'update', 'Account=%s_cpu' % acct, 'JobId=%s' % str(jobid)])
    # os.system('scontrol update Account=%s_cpu JobId=%s' % (acct, str(jobid)) )


def getaccounts(sq, stage):
    accounts = {}
    for q in sq:
        if not q == '':
            splits = q.split()
            pid = splits[0]
            account = splits[2]
            account = account.split("_")[0]
            if not account in accounts:
                accounts[account] = {}
            accounts[account][pid] = splits
#     if len(accounts.keys()) == 3 and stage != 'final': # all accounts have low priority ### use 3 when using RAC
    if len(accounts.keys()) == 2 and stage != 'final': # all accounts have low priority   ### use 2 when not using RAC
        print('all accounts have low priority, leaving queue as-is')
        announceacctlens(accounts, True)
        exit()
    return accounts


def getbalance(accounts, num):
    sums = 0
    for account in accounts:
        sums += len(accounts[account].keys())
    bal = math.ceil(sums/num)
    print('bal%i %i= ' % (num, bal))
    return bal


def checknumaccts(accts,checking,mc):
    # len(accounts) will never == 2 after pop, since I checked for len(accounts) == 3
    if len(accts.keys()) == 0:
        if checking == 'RAC':
            print('RAC has low priority status, skipping RAC as taker')
        else:
            print('moved %s jobs to RAC' % str(mc))
        exit()


def redistribute4G(accounts,bal):
    RAC = 'rrg-yeaman'
    if RAC in accounts:   # no need to redistribute to RAC if RAC has low priority
        accounts.pop(RAC) # drop RAC from list to redistribute, exit if nothing to redistribute
        checknumaccts(accounts, 'RAC', '')    # if all jobs are on RAC, exit
        return accounts
    keys = list(accounts.keys())
    print('before loop %s' % keys)
    for account in keys:
        # distribute 4G jobs to RAC
        pids = list(accounts[account].keys())
        mcount = 0
        for pid in pids:
            mem = int([m for m in accounts[account][pid] if m.endswith('M')][0].split("M")[0])
            if mem <= 4000:
                # if it can be scheduled on the RAC, change the account of the jobid, and remove jobid from list
                adjustjob(RAC,pid)
                accounts[account].pop(pid)
                mcount += 1
                if mcount == bal:
                    break
        print("distributed {} jobs from {} to RAC".format(mcount, account))
        if len(accounts[account].keys()) == 0:
            accounts.pop(account)
    checknumaccts(accounts, 'none', mcount) # if all jobs were redistributed to the RAC, exit
    return accounts


def gettaker(accounts):
    keys = list(accounts.keys())
    if len(keys) == 2:
        # if there are two accounts, figure out which account has more
        maxx = 0
        for acct in keys:
            if len(accounts[acct]) > maxx:
                giver = acct
                maxx = len(accounts[acct])
    else:
        assert len(keys) == 1
        giver = keys[0]
    taker = list(set(['def-saitken','def-yeaman']).symmetric_difference(set([giver])))[0]
    return giver, taker


def givetotaker(giver,taker,accounts,bal):
    taken = 0
    pids = list(accounts[giver].keys())
    numtotake = len(pids) - bal
    if bal == 1 and len(pids) == 1:
        numtotake = 1
    printout = 'giver has {} jobs to give. (bal= {}). Giver ({}) is giving {} jobs to taker ({})'.format(len(pids),bal,giver,numtotake,taker)
    print("\\t %s" % printout)
    if numtotake > 0:
        for pid in pids[::-1]: # re-assign the newer jobs, hopefully older jobs will eventually run
            adjustjob(taker,pid)
            taken += 1
            if taken == numtotake:
                print("\\t redistributed %s jobs from %s to %s" % (str(taken),giver,taker))
                break
    else:
        print("\t giver sees that taker has enough, so giver is not giving")


def main(thisfile,phase):
    globals().update({'thisfile': thisfile, 'phase': phase})
    # get the queue
    sq = getsq(grepping = [phase,'Priority'], status = ['PD'])

    # get per-account counts of jobs in Priority pending status, exit if all accounts have low priority
    accts = getaccounts(sq, '')
    announceacctlens(accts, False)

#     # figure out how many to balance remaining
#     balance = getbalance(accts,3)

#     # redistribute 4G jobs to RAC unless RAC has low priority, exit if all jobs redistributed or no jobs to redistribute
#     accts = redistribute4G(accts,balance)

    # figure out which account to add to
    giver, taker = gettaker(accts)

    # redistribute to taker
    balance = getbalance(accts,2)
    givetotaker(giver, taker, accts, balance)

    # announce final job counts
    announceacctlens(getaccounts(getsq(grepping = [phase, 'Priority']),
                                 'final'),
                     True)


if __name__ == '__main__':
    # args
    thisfile, phase = sys.argv

    main(thisfile, phase)





