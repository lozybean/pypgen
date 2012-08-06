#!/usr/local/epd7/bin/python python
# encoding: utf-8
"""
sync2Fst.py

Created by Nicholas Crawford (c) 2010 Nicholas Crawford. All rights reserved.

"""

import os
import re
import sys
import argparse

def interface():
	p = argparse.ArgumentParser()
	p.add_argument('-i','--input-file',
        help='Path to input file.')
	p.add_argument('-o','--output-file',
        help='Path to output file.')
	args = p.parse_args()
 	return args

def calc_SNP_freqs(pops):

	def freq(value,total_count):
		"""Avoid divide by zero errors"""
		if total_count == 0.0:
			return value
		else:
			return value/total_count

	frequencies = []
	coverage = []
	for pop in pops:
		counts =  [float(value) for value in pop.split(":")]
		total_count = float(sum(counts))
		coverage.append(total_count)
		freqs = [freq(value, total_count) for value in counts]
		frequencies.append(freqs)

	return (frequencies, coverage)


def harmonic_mean(values):
    """calculates harmonic mean from list of integers"""
    
    fractional_counts = sum([1.0/v for v in values ])
    harmonic_mean = float(len(values))/fractional_counts

    return harmonic_mean

def harmonic_mean_chao(values):
    """Calculates the harmonic mean following the method suggested by
    Anne Chao. The formula is: 1/[(1/A)+var(D)(1/A)**3]. Used for 
    calculating multilocus Dest."""
    
    count = float(len(values))
    A = sum(values)/count
    varD = sum([(v-A)**2 for v in values])/count
    harmonic_mean_chao = 1/((1/A)+(varD)*pow((1/A),3))
    return harmonic_mean_chao


def Hs_prime_est(allele_freqs, n):
    """Calculate corrected Hs: the mean within-subpopulation 
    heterozygosity (Nei and Chesser 1983)."""

    Hj = [1.0-sum([freq**2 for freq in pop[:4]]) for pop in allele_freqs]
    Hs_prime_est = 1/n * sum(Hj)
    return Hs_prime_est

def Hs_est(Hs_prime_est,harm_mean):
    """ Basic Equation: ((2*N_harmonic)/(2*N_harmonic-1))*Hs"""
    
    Hs = Hs_prime_est
    Hs_est = ((2.0*harm_mean)/(2.0*harm_mean-1.0))*Hs
    return Hs_est

def Ht_prime_est(allele_freqs,n):
    """Calculate corrected Ht: the heterozygosity of the pooled 
    subpopulations (Nei and Chesser 1983)"""

    inner = [(1/n*sum(allele_list))**2 for allele_list in zip(*allele_freqs)[:4]]
    Ht_prime_est = 1.0-sum(inner)
    return Ht_prime_est

def Ht_est(Ht_p_est,Hs_est,harm_mean,n):
    """Basic Equation: Ht+Hs_est/(2*N_harmonic*n)"""
    
    Ht = Ht_p_est
    Ht_est = Ht+Hs_est/(2.0*harm_mean*n)
    return Ht_est

def Gst_est(Ht_est, Hs_est):
    """Gst = (Ht-Hs)/Ht"""

    if Ht_est == 0.0: return 0.0 
    Gst_est = (Ht_est-Hs_est)/Ht_est
    return Gst_est

def G_prime_st_est(Ht_est, Hs_est, Gst_est, n):
    
    if (n-1.0)*(1.0-Hs_est) == 0: return 0.0
    G_prime_st = (Gst_est*(n-1.0+Hs_est))/((n-1.0)*(1.0-Hs_est))
    return G_prime_st

def G_double_prime_st_est(Ht_est, Hs_est, n):
    """G''st = k*(HT-HS)/((k*HT-HS)*(1-HS)"""
    
    if (n*Ht_est-Hs_est)*(1-Hs_est) == 0.0: return 0.0 
    G_double_prime_st_est = n*(Ht_est-Hs_est)/((n*Ht_est-Hs_est)*(1-Hs_est))
    return  G_double_prime_st_est

def D_est(Ht_est, Hs_est, n):
    
    if ((1.0-Hs_est))*(n/(n-1)) == 0.0: return 0.0
    D_est = ((Ht_est-Hs_est)/(1.0-Hs_est))*(n/(n-1))
    return D_est

def main():
	
	args = interface()

	Ns = [10,8]
	n = float(len(Ns))
	Ns_harm = harmonic_mean(Ns)
	Ns_harm_chao = harmonic_mean_chao(Ns)

	fin = open(args.input_file,'rU')
	fout =  open(args.output_file,'w')
	
	for count, line in enumerate(fin):
		line_parts = line.strip().split()
		
		# CALCULATE BASIC STATS
		chrm, pos, refbase = line_parts[:3]
		pops = line_parts[3:]
		allele_freqs, coverage = calc_SNP_freqs(pops)
		min_coverage = min(coverage)
		max_coverage = max(coverage)

		# CALCULATE Hs AND Ht
		Hs_prime_est_ = Hs_prime_est(allele_freqs,n)
		Ht_prime_est_ = Ht_prime_est(allele_freqs,n)
		Hs_est_ = Hs_est(Hs_prime_est_, Ns_harm)
		Ht_est_ = Ht_est(Ht_prime_est_,Hs_est_,Ns_harm,n)

		# CALCULATE F-STATISTICS
		Gst_est_ = Gst_est(Ht_est_, Hs_est_)
		G_prime_st_est_ = G_prime_st_est(Ht_est_, Hs_est_, Gst_est_, n)
		G_double_prime_st_est_ = G_double_prime_st_est(Ht_est_, Hs_est_, n)
		D_est_ = D_est(Ht_est_, Hs_est_, n)
		

		# PRINT OUTPUT
		values = [chrm, pos, refbase, min_coverage, max_coverage, Hs_est_, \
		Ht_est_, Gst_est_, G_prime_st_est_, G_double_prime_st_est_, D_est_,]
		result =  ','.join([str(item) for item in values])+"\n"
		fout.write(result)

	fin.close()
	fout.close()


if __name__ == '__main__':
	main()



