# -*- coding: utf-8 -*-
"""
Created on Mon Sep 27 10:47:32 2021

@author: Oli
"""

import pytest 
import pandas as pd
import numpy as np
import netCDF4 as nc
import os

os.chdir(os.path.dirname(os.path.realpath(__file__)))
exec(open("test_setup.py").read())

os.chdir(real_dat_path)
exec(open("local_load_up.py").read())

os.chdir(str(test_dat_path) + '\R_outputs')
R_results = pd.read_csv('Arson_2002.csv')

from Core_functionality.Trees.Transfer_tree import define_tree_links, predict_from_tree, update_pars, predict_from_tree_fast
from Core_functionality.prediction_tools.regression_families import regression_link, regression_transformation

from model_interface.wham import WHAM
from Core_functionality.AFTs.agent_class import AFT

from Core_functionality.AFTs.arable_afts import Swidden, SOSH, MOSH, Intense_arable
from Core_functionality.AFTs.livestock_afts import Pastoralist, Ext_LF_r, Int_LF_r, Ext_LF_p, Int_LF_p
from Core_functionality.AFTs.forestry_afts  import Agroforestry, Logger, Managed_forestry, Abandoned_forestry  
from Core_functionality.AFTs.nonex_afts  import Hunter_gatherer, Recreationalist, SLM, Conservationist

from Core_functionality.AFTs.land_system_class import land_system
from Core_functionality.AFTs.land_systems import Cropland, Pasture, Rangeland, Forestry, Urban, Unoccupied, Nonex

from Core_functionality.top_down_processes.arson import arson
from Core_functionality.top_down_processes.background_ignitions import background_rate
from Core_functionality.top_down_processes.fire_constraints import fuel_ct, dominant_afr_ct


#####################################################################

### Run model year then reproduce outputs

#####################################################################

all_afts = [Swidden, SOSH, MOSH, Intense_arable, 
            Pastoralist, Ext_LF_r, Int_LF_r, Ext_LF_p, Int_LF_p,
            Agroforestry, Logger, Managed_forestry, Abandoned_forestry, 
             Hunter_gatherer, Recreationalist, SLM, Conservationist]

parameters = {
    
    'xlen': 192, 
    'ylen': 144,
    'AFTs': all_afts,
    'LS'  : [Cropland, Rangeland, Pasture, Forestry, Nonex, Unoccupied, Urban],
    'Fire_types': {'cfp': 'Vegetation', 'crb': 'Arable', 'hg': 'Vegetation', 
                   'pasture': 'Pasture', 'pyrome': 'Vegetation'}, 
    'Observers': {'arson': arson, 'background_rate': background_rate},
    'AFT_pars': Core_pars,
    'Maps'    : Map_data,
    'Constraint_pars': {'Soil_threshold': 0.1325, 
                        'Dominant_afr_threshold': 0.5, 
                        'Rangeland_stocking_contstraint': True, 
                        'R_s_c_Positive' : False, 
                        'HG_Market_constraint': 7800, 
                        'Arson_threshold': 0.5},
    'timestep': 13,
    'end_run' : 13,
    'reporters': ['Managed_fire', 'Background_ignitions','Arson'],
    'theta'    : 0.1,
    'bootstrap': False, 
    'Seasonality': False
    
    }


mod = WHAM(parameters)

### setup
mod.setup()

### ignite
mod.go()

#################################################################

### tests - run code to reproduce model output

#################################################################

### tree code

x, b = 'arson', 'bool'

    
mod.Observers['arson'][0].Fire_dat['arson']['bool'] = mod.Observers['arson'][0].Fire_dat['arson']['bool'].iloc[:, 0:2]
Fire_struct = define_tree_links(mod.Observers['arson'][0].Fire_use[x][b]['pars'])

tree = predict_from_tree_fast(dat = mod.Observers['arson'][0].Fire_dat[x][b], 
                              tree = mod.Observers['arson'][0].Fire_use[x][b]['pars'], struct = Fire_struct, 
                               prob = 'yprob.TRUE', skip_val = -3.3999999521443642e+38, na_return = 0)

     
### regression code   
errors = []
    
reg = mod.Observers['arson'][0].Fire_dat['arson']['ba'].Market_access * 2.9037 - 0.49
reg = 1/(1+np.exp(0-reg))
reg_m = np.nanmean(reg)
reg = [x if x >= 0.5 else 0 for x in reg]

combo = (reg + tree) / 2


afr_vals = []
    
### Assume Nonex doesn't commit arson
for ls in ['Cropland', 'Pasture', 'Rangeland', 'Forestry']:
        
    if 'Trans' in mod.LFS[ls].keys():
                
        afr_vals.append(mod.LFS[ls]['Trans'])
        
        ### remove agroforestry from logging contribution to arson
if 'Agroforestry' in mod.AFT_scores.keys():
            
   afr_vals.append(0 - mod.AFT_scores['Agroforestry'])
        
afr_vals = np.nansum(afr_vals, axis = 0)        
afr_vals = pd.Series([x if x > 0 else 0 for x in np.array(afr_vals).reshape(mod.p.xlen*mod.p.ylen)])
  
igs = combo * np.exp(afr_vals * 1.166 -2.184) * mod.p.Maps['Mask']  


###########################################################################################

### tests

###########################################################################################


def test_tree():
    
    errors = []
    
    if any([x not in (mod.Observers['arson'][0].Fire_use['arson']['bool']['pars']['yprob.TRUE'].tolist()) for x in (tree.tolist())]):
        
        errors.append("Errors in tree prediction values")
    
    assert not errors, "errors occured:\n{}".format("\n".join(errors))
    
    
def test_regression():

    errors = []
    
    if not all(pd.Series(reg).describe()[3:6] == 0):
        
        errors.append("Errors in regression prediction values")

    if not np.nanmax(pd.Series(reg) <= 1):
        
        errors.append("Errors in regression prediction values")

    if not np.nanmean(reg) < reg_m:
        
        errors.append("Errors in regression prediction values")
    
    assert not errors, "errors occured:\n{}".format("\n".join(errors))
        
    
def test_combined_mod():   
    
    assert(np.nanmin(combo)  == 0 and np.nanmax(combo)  <= 1)
    

def test_arson_ignitions():   


    assert(np.nanmean(igs) == np.nanmean(mod.Observers['arson'][0].Fire_vals))

    
def test_arson_output():
    
    igs_r = igs[R_results.iloc[:, 0].notnull()]
    
    errors = []
    
    if not (np.nanmax(igs_r) == pytest.approx(np.nanmax(R_results.iloc[:, 0]), 0.1)):
        
        errors.append("Arson outputs don't match baseline calculations")
    
    if not (np.nanmedian(igs_r) == pytest.approx(np.nanmedian(R_results.iloc[:, 0]), 0.1)):
        
        errors.append("Arson outputs don't match baseline calculations")
        
    if not (np.nanquantile(igs_r, 0.75) == pytest.approx(np.nanquantile(R_results.iloc[:, 0], 0.75), 0.1)):
        
        errors.append("Arson outputs don't match baseline calculations")

    assert not errors, "errors occured:\n{}".format("\n".join(errors))

