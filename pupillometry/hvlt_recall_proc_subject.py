# -*- coding: utf-8 -*-
"""
Created on Fri Sep 16 12:00:45 2016

@author: jelman

This script takes Tobii .gazedata file from HVLT recall-rocgnition as input. It 
first performs interpolation and filtering, The first 1 sec of recall instructions 
is used as baseline. Dilation at each second is produced. 

Some procedures and parameters adapted from:
Jackson, I. and Sirois, S. (2009), Infant cognition: going full factorial 
    with pupil dilation. Developmental Science, 12: 670-679. 
    doi:10.1111/j.1467-7687.2008.00805.x

Hoeks, B. & Levelt, W.J.M. Behavior Research Methods, Instruments, & 
    Computers (1993) 25: 16. https://doi.org/10.3758/BF03204445
"""

from __future__ import division, print_function, absolute_import
import os
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import pupil_utils
try:
    # for Python2
    import Tkinter as tkinter
    import tkFileDialog as filedialog
except ImportError:
    # for Python3
    import tkinter
    from tkinter import filedialog


def plot_trials(pupildf, fname):
    sns.set_style("ticks")
    palette = sns.color_palette("deep", n_colors=len(pupildf.Trial.unique()))
    p = sns.lineplot(data=pupildf, x="Timestamp",y="Dilation", hue="Trial", palette=palette, legend="brief")
    plt.xticks(rotation=45)
    plt.tight_layout()
    plt.legend(loc='best')
    plot_outname = pupil_utils.get_proc_outfile(fname, "_PupilPlot.png")
    p.figure.savefig(plot_outname)
    plt.close()
    
    
def clean_trials(df, trialevents):
    resampled_dict = {}
    for trialnum in trialevents.Trial.unique():
        basestart, basestop, respstart, respstop =  trialevents.loc[trialevents.Trial==trialnum,'TETTime']
        condition = trialevents.loc[trialevents.Trial==trialnum,'Condition'].iat[0]
        rawtrial = df.loc[(df.TETTime>=basestart) & (df.TETTime<=respstop)]
        rawtrial.loc[(rawtrial.TETTime>=basestart) & (rawtrial.TETTime<=basestop),'Phase'] = 'Baseline' 
        rawtrial.loc[(rawtrial.TETTime>=respstart) & (rawtrial.TETTime<=respstop),'Phase'] = 'Response' 
#        rawtrial = rawtrial[rawtrial.Condition=='Response']
        cleantrial = pupil_utils.deblink(rawtrial)
        trial_resamp = pupil_utils.resamp_filt_data(cleantrial, filt_type='low', string_cols=['CurrentObject', 'Phase'])
        baseline = trial_resamp['DiameterPupilLRFilt'].first('2000ms').mean()
#        baseline = trial_resamp.DiameterPupilLRFilt.iat[0]
        trial_resamp['Baseline'] = baseline
        trial_resamp['Dilation'] = trial_resamp['DiameterPupilLRFilt'] - trial_resamp['Baseline']
        trial_resamp = trial_resamp[trial_resamp.Phase=='Response']
        trial_resamp['Condition'] = condition
        resampled_dict[trialnum] = trial_resamp        
    dfresamp = pd.concat(resampled_dict, names=['Trial','Timestamp'], sort=True)
    return dfresamp
    

def get_trial_events(df):
    """
    Create dataframe of trial events. This includes:
        Condition: ['Letter', 'Category']
        Trial: [1, 2, 3, 4, 5, 6]
        TrialPhase = ['Baseline', 'Response']
        StartStop = ['Start', 'Stop']
    First finds timestamps where CurrentObject changes to determine starts and stops.
    Combines these and defines trial, phase and whether it is start or stop time. 
    """
    startidx = df['CurrentObject'].ne(df['CurrentObject'].shift().ffill()).astype(bool)
    stopidx = df['CurrentObject'].ne(df['CurrentObject'].shift(-1).bfill()).astype(bool)
    trialevents_start = pd.DataFrame(df.loc[startidx, ['TETTime','CurrentObject']])
    trialevents_stop = pd.DataFrame(df.loc[stopidx, ['TETTime','CurrentObject']])
    trialevents_start = trialevents_start.loc[(trialevents_start.CurrentObject=="ReadLetter") | 
                                              (trialevents_start.CurrentObject == "RecordLetter")]
    trialevents_stop = trialevents_stop.loc[(trialevents_stop.CurrentObject=="BeginFile") | 
                                            (trialevents_stop.CurrentObject == "RecordLetter")]
    trialevents_start['TrialPhase'] = np.tile(['Baseline','Response'], 6)
    trialevents_start['StatStop'] = 'Start'
    trialevents_stop['TrialPhase'] = np.tile(['Baseline','Response'], 6)
    trialevents_stop['StartStop'] = 'Stop'
    trialevents = trialevents_start.append(trialevents_stop).sort_index()
    trialevents['Trial'] = np.repeat(range(1,7), 4)
    trialevents['Condition'] = np.repeat(['Letter', 'Category'], 12)
    return trialevents

   
def proc_subject(filelist):
    """Given an infile of raw pupil data, saves out:
        1. Session level data with dilation data summarized for each trial
        2. Dataframe of average peristumulus timecourse for each condition
        3. Plot of average peristumulus timecourse for each condition
        4. Percent of samples with blinks """
    for fname in filelist:
        print('Processing {}'.format(fname))
        if (os.path.splitext(fname)[-1] == ".gazedata") | (os.path.splitext(fname)[-1] == ".csv"):
            df = pd.read_csv(fname, sep="\t")
        elif os.path.splitext(fname)[-1] == ".xlsx":
            df = pd.read_excel(fname)
        else: 
            raise IOError('Could not open {}'.format(fname))
        df = df[df.CurrentObject.str.contains("Recall", na=False)]
        df = pupil_utils.deblink(df)
        dfresamp = pupil_utils.resamp_filt_data(df, filt_type='low', string_cols=['CurrentObject'])
        
        
        dfresamp = clean_trials(df, trialevents)
        dfresamp = dfresamp.reset_index(drop=False).set_index(['Condition','Trial'])
        dfresamp['Timestamp'] = dfresamp.groupby(level='Trial')['Timestamp'].transform(lambda x: x - x.iat[0])
        dfresamp1s = dfresamp.groupby(level=['Condition','Trial']).apply(lambda x: x.resample('1S', on='Timestamp', closed='right', label='right').mean())
        pupilcols = ['Subject', 'Trial', 'Condition', 'Timestamp', 'Dilation',
                     'Baseline', 'DiameterPupilLRFilt', 'BlinksLR']
        pupildf = dfresamp1s.reset_index()[pupilcols].sort_values(by=['Trial','Timestamp'])
        pupildf = pupildf[pupilcols].rename(columns={'DiameterPupilLRFilt':'Diameter',
                                         'BlinksLR':'BlinkPct'})
        pupildf['Timestamp'] = pd.to_datetime(pupildf.Timestamp).dt.strftime('%H:%M:%S')
        pupil_outname = pupil_utils.get_proc_outfile(fname, '_ProcessedPupil.csv')
        pupildf.to_csv(pupil_outname, index=False)
        plot_trials(pupildf, fname)



    
if __name__ == '__main__':
    if len(sys.argv) == 1:
        print('')
        print('USAGE: {} <raw pupil file> '.format(os.path.basename(sys.argv[0])))
        print('Processes single subject data from fluency task and outputs csv')
        print('files for use in further group analysis.')
        print('Takes eye tracker data text file (*.gazedata) as input.')
        print('Removes artifacts, filters, and calculates dilation per 500ms.')
        print('')
        root = tkinter.Tk()
        root.withdraw()
        # Select files to process
        filelist = filedialog.askopenfilenames(parent=root,
                                              title='Choose HVLT recall-recognition pupil gazedata file to process',
                                              filetypes = (("gazedata files","*.gazedata"),
                                                           ("all files","*.*")))       
        filelist = list(filelist)
        # Run script
        proc_subject(filelist)

    else:
        filelist = [os.path.abspath(f) for f in sys.argv[1:]]
        proc_subject(filelist)
