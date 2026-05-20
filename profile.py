#! /usr/bin/python3

"""This profiling routine was used to identify bottlenecks,
then in objects.base the getRange method was optimized.
It still is the main bottleneck,
but there seems to be no potential for further optimization.

Now you should modify/copy this file,
to profile your AI source code.

In some tournaments, there is a penalty for computation cost."""

import sys
from cProfile import Profile

# only in python3.3
from pstats import Stats
from time import perf_counter

print("You can supply an alternative config file on the command-line")
print("You should stop Wesen by Ctrl+C to finish profiling")

sys.argv.append("--disablegui")
pr = Profile(perf_counter)
pr.run("Loader()")
pr.dump_stats("profile.stats")
# you may explore profile.stats with the pstats browser.

stats = Stats(pr)

stats.sort_stats("tottime")
# stats.print_stats('Wesen/sources',10)
stats.print_stats("Wesen/", 10)
