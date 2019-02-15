#!/usr/bin/env python
# Copyright (c) Microsoft Corporation. All rights reserved.
# Licensed under the MIT License.
#
import getopt, sys, time



def calcPiNewton(digits):
# Newtons formula for PI is:
# PI / 2 = sum_n_from_0_to_inf(n! / (2 * n + 1)!!)

# This can be written as:
# PI / 2 = 1 + 1/3 * (1 + 2/5 * (1 + 3/7 * (1 + 4/9 * (1 + ... ))))

# This algorithm puts 2 * 1000 on the right side and computes everything from inside out.

    scale = 10000
    maxarr = int(digits/4) * 14
    arrinit = 2000
    carry = 0
    arr = []
    output = ''

    # initialize the array
    arr = [arrinit]*(maxarr+1)
        
    for i in range(maxarr, 1, -14):
        sum = 0
        for j in range(i, 0, -1):
            sum = (sum * j) + (scale * arr[j])
            arr[j] = sum % ( (j*2)-1 )
            sum = sum / ((j*2)-1)
        output += "%04d" % (carry + (sum / scale))
        carry = sum % scale
    
    return output

    
def usage():
    print 'Calculate pi to x digits.  Usage: python pi.py [digits]'


def main():
    try:
        opts, args = getopt.getopt(sys.argv[1:], "h", ["help"])
    except getopt.GetoptError:
        # print help information and exit:
        usage()
        sys.exit(2)

    for o, a in opts:
        if o == "-v":
            verbose = True
        if o in ("-h", "--help"):
            usage()
            sys.exit()
    
    if args:
        digits = int(args[0])
        if digits < 1:
            print 'Not a valid number of digits: %s' % digits
    else:
        digits = 1000
        print 'Calculating the default number of pi digits (%s)' % digits
        
    # do the calculation
    start_time = time.time()
    print calcPiNewton(digits)
    end_time = time.time()
    print "TotalTime=%f" %(end_time-start_time)
        
    

if __name__ == "__main__":
    main()