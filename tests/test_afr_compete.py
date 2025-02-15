# -*- coding: utf-8 -*-
"""
Created on Wed Jun 30 10:25:15 2021

@author: Oli
"""

import pytest 
import pandas as pd
import numpy as np
import netCDF4 as nc
import os

os.chdir(os.path.dirname(os.path.realpath(__file__)))
exec(open("test_setup.py").read())

from Core_functionality.Trees.Transfer_tree import define_tree_links, predict_from_tree
from Core_functionality.AFTs.agent_class import AFT, dummy_agent
from Core_functionality.AFTs.afts import SOSH, Intense_arable
from model_interface.wham import WHAM


#########################################################################

### Load test data

#########################################################################

os.chdir(str(test_dat_path) + '\AFTs')
Dummy_frame   = pd.read_csv('Dummy_pars.csv')
Dummy_dat     = nc.Dataset('Test.nc')
Dummy_dat     = Dummy_dat['Forest_frac'][:]
Map_data      = {'Test': Dummy_dat}
Map_test      = np.array(pd.read_csv('Test_raster.csv'))

### Mock load up
Core_pars = {'AFT_dist': {}, 
             'Fire_use': {}} 

Core_pars['AFT_dist']['Test/Test']          = Dummy_frame
Core_pars['AFT_dist']['Sub_AFTs/Test_Test'] = Dummy_frame

### Mock model
parameters = {
    
    'xlen': 144, 
    'ylen': 192,
    'AFTs': [dummy_agent],
    'LS'  : [],
    'AFT_pars': Core_pars,
    'Maps'    : Map_data,
    'timestep': 0,
    'theta'    : 0.1, 
    'bootstrap': False, 
    'Observers': {},
    'reporters': []
    
    }


##########################################################################

### tests

##########################################################################

def test_afr_compete():
    
    errors = []
    
    mod = WHAM(parameters)
    mod.setup()
    mod.agents.setup()
    mod.agents.get_pars(mod.p.AFT_pars)
    mod.agents.compete()
    
    if not len([x for x in mod.agents.Dist_vals[0] if x <= mod.p.theta and x > 0]) == 0:
        errors.append("theta parameter did not function correctly")
    
    if not [x for x in mod.agents.Dist_vals[0]][0:8] == [0.426087]*8:
        errors.append("False negatives in model prediction tree")
        
    if not [x for x in mod.agents.Dist_vals[0]][8:] == [0]*27640:
        errors.append("False positives in model prediction tree")
        
    assert not errors, "errors occured:\n{}".format("\n".join(errors))
    


