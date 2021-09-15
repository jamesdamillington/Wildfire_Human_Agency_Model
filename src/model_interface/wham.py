# -*- coding: utf-8 -*-
"""
Created on Tue Jun 22 10:41:39 2021

@author: Oli
"""


import agentpy as ap
import numpy as np
import pandas as pd
from copy import deepcopy


from Core_functionality.AFTs.agent_class import AFT
from Core_functionality.AFTs.arable_afts import Swidden, SOSH, MOSH, Intense_arable
from Core_functionality.AFTs.livestock_afts import Pastoralist, Ext_LF_r, Int_LF_r, Ext_LF_p, Int_LF_p
from Core_functionality.AFTs.forestry_afts  import Agroforestry, Logger, Managed_forestry, Abandoned_forestry  
from Core_functionality.AFTs.nonex_afts  import Hunter_gatherer, Recreationalist, SLM, Conservationist
from Core_functionality.AFTs.land_system_class import land_system
from Core_functionality.AFTs.land_systems import Cropland, Pasture, Rangeland, Forestry, Urban, Unoccupied, Nonex

from Core_functionality.top_down_processes.arson import arson
from Core_functionality.top_down_processes.background_ignitions import background_rate
from Core_functionality.top_down_processes.fire_constraints import fuel_ct, dominant_afr_ct, hg_urban_ct

from Core_functionality.Trees.Transfer_tree import define_tree_links, predict_from_tree, update_pars, predict_from_tree_fast
from Core_functionality.prediction_tools.regression_families import regression_link, regression_transformation


###################################################################

### Core model class

###################################################################


class WHAM(ap.Model):

    def setup(self):

        # Parameters
        self.xlen = self.p.xlen
        self.ylen = self.p.ylen

        # Create grid
        self.grid = ap.Grid(self, (self.xlen, self.ylen), track_empty=False)
        
        
        # Create land systems
        self.ls     = ap.AgentList(self, 
                       [y[0] for y in [ap.AgentList(self, 1, x) for x in self.p.LS]])
        
        # Create AFTs
        self.agents = ap.AgentList(self, 
                       [y[0] for y in [ap.AgentList(self, 1, x) for x in self.p.AFTs]])


        # Create Observers
        self.Observers = dict(zip([x for x in self.p.Observers.keys()], 
                                  [ap.AgentList(self, 1, y) for y in self.p.Observers.values()]))
        

        ########################################
        ### Agent class setup
        ########################################
        
        ### LS
        self.ls.setup()
        self.ls.get_pars(self.p.AFT_pars)
        self.ls.get_boot_vals(self.p.AFT_pars)
        
        ### AFTs
        self.agents.setup()
        self.agents.get_pars(self.p.AFT_pars)
        self.agents.get_boot_vals(self.p.AFT_pars)
        self.agents.get_fire_pars()
    
        ### Observers
        for observer in self.Observers.keys():
            
            self.Observers[observer].setup()
        
        if 'background_rate' in self.Observers.keys():
            
            self.Observers['background_rate'].get_fire_pars()
        
        if 'arson' in self.Observers.keys():
            
            self.Observers['arson'].get_fire_pars()
        
        ### Results containers
        self.results = {}
        
        for i in self.p.reporters:
            
            self.results[i] = []
        
    
    def go(self):
        
        while self.p.timestep <= self.p.end_run:
    
            self.step()
            print(self.p.timestep)
            
            
    ########################################################################
    
    ### AFT distribution functions
    
    ########################################################################
    
    def allocate_X_axis(self):
        
        ### Gather X-axis vals from land systems       
        ls_scores    = dict(zip([type(x).__name__ for x in self.ls], 
                        [x.Dist_vals for x in self.ls]))
        
        #################################################
        ### Perform calculation to get X_axis
        #################################################
        
        ### Forestry
        ls_scores['Forestry'] =  ls_scores['Forestry'] * (1 - ls_scores['Nonex']['Forest']) * (1 - ls_scores['Unoccupied'])
        
        ### Non-ex & Unoccupied
        Open_vegetation                =  self.p.Maps['Mask'] - ls_scores['Cropland'] - ls_scores['Pasture'] - ls_scores['Rangeland'] - ls_scores['Forestry'] - ls_scores['Urban']
        Open_vegetation                =  np.array([x if x >=0 else 0 for x in Open_vegetation])
        ls_scores['Nonex']['Combined'] =  Open_vegetation * (ls_scores['Nonex']['Other'] / (ls_scores['Nonex']['Other'] + ls_scores['Unoccupied']))
        ls_scores['Unoccupied']        =  Open_vegetation * (ls_scores['Unoccupied'] / (ls_scores['Nonex']['Other'] + ls_scores['Unoccupied']))
        ls_scores['Nonex']             =  ls_scores['Nonex']['Combined']
        
        ### There is an issue with alignment of data sets giving LC > land mask (see forestry)
        ### Current workaround...
        
        ls_frame                       = pd.DataFrame(ls_scores)
        ls_frame['tot']                = self.p.Maps['Mask'] / ls_frame.sum(axis = 1) 
        ls_frame.iloc[:, 0:-1  ]       = ls_frame.iloc[:,0:-1].multiply(ls_frame.tot, axis="index")                            
        ls_frame                       = ls_frame.iloc[:, 0:-1].to_dict('series')
        
        ### reshape and stash
        self.X_axis                    =  dict(zip([x for x in ls_frame.keys()], 
                                            [np.array(x).reshape(self.ylen, self.xlen) for x in ls_frame.values()]))
        
    
    def allocate_Y_axis(self):
        
        ### Gather Y-axis scores from AFTs
        
        land_systems = [y for y in pd.Series([x for x in self.agents.ls]).unique()]
        afr_scores   = {}
    
    
        if type(land_systems) == str:
            land_systems = [land_systems] #catch the case where only 1 ls type
            
        for l in land_systems:
            
            ### get predictions
            afr_scores[l] = [x.Dist_vals for x in self.agents if x.ls == l]
                
            ### remove dupes - this only works with more than 1 AFR per LS
            unique_arr    = [np.array(x) for x in set(map(tuple, afr_scores[l]))]
            
            ### calculate total by land system by cell
            tot_y         = np.add.reduce(unique_arr)
            
            ### divide by total & reshape to world map
            afr_scores[l] = [np.array(x / tot_y).reshape(self.ylen, self.xlen) for x in afr_scores[l]]
               
        
            ### Here - multiply Yscore by X-axis
            afr_scores[l] = dict(zip([x.afr for x in self.agents if x.ls == l], 
                             [y * self.X_axis[l] for y in afr_scores[l]]))
        
        ### stash afr scores
        self.LFS = afr_scores
        
        
    def allocate_AFT(self):
        
        AFT_scores   = {}
        
        ### Loop through agents and assign fractional coverage
        for a in self.agents:
            
            if a.sub_AFT['exists'] == False:
            
                AFT_scores[type(a).__name__] = self.LFS[a.ls][a.afr]
                
            elif a.sub_AFT['exists'] == True:
                
                ### Where AFT is a fraction of a single LFS
                if a.sub_AFT['kind'] == 'Fraction':
                    
                    a.AFT_vals                   = np.array(a.AFT_vals).reshape(self.ylen, self.xlen)
                    AFT_scores[type(a).__name__] = self.LFS[a.ls][a.afr] * a.AFT_vals
                    
                    
                ### Where AFT is a whole LFS plus a fraction of another
                elif a.sub_AFT['kind'] == 'Addition':
                    
                    a.AFT_vals                   = np.array(a.AFT_vals).reshape(self.ylen, self.xlen)
                    AFT_scores[type(a).__name__] = self.LFS[a.ls][a.afr] + (self.LFS[a.sub_AFT['ls']][a.sub_AFT['afr']] * a.AFT_vals)
                
                
                ### Where AFT is a fraction of several LFS
                elif a.sub_AFT['kind'] == 'Multiple':
                    
                    AFT_scores[type(a).__name__] = np.zeros([self.ylen, self.xlen])
                
                    for i in range(len(a.sub_AFT['afr'])):
                        
                        temp_vals                    = np.array(a.AFT_vals[i]).reshape(self.ylen, self.xlen)
                        AFT_scores[type(a).__name__] = AFT_scores[type(a).__name__] + (self.LFS[a.sub_AFT['ls'][i]][a.sub_AFT['afr'][i]] * temp_vals)
                
        self.AFT_scores = AFT_scores
    
    
    ###################################################################################
    
    ### Fire use functions
    
    ###################################################################################
    
    def calc_BA(self, group_by = str):
        
        ''' gathers deliberate fire and multiplies by AFT coverage'''
        
        
        if group_by == 'Fire_type':
        
            self.Managed_fire = {}
        
            for i in self.p.Fire_types.keys():
            
                self.Managed_fire[i] = {}
            
                for a in self.agents:
                    
                    if i in a.Fire_vals.keys():
                    
                        self.Managed_fire[i][a] = np.array(a.Fire_vals[i]).reshape(self.p.ylen, self.p.xlen)
                        self.Managed_fire[i][a] = self.Managed_fire[i][a] * self.AFT_scores[type(a).__name__]
            
                self.Managed_fire[i] = np.nansum([x for x in self.Managed_fire[i].values()], 
                                                 axis = 0)
                
        elif group_by == 'Land_cover':
            
            self.Managed_fire = {}
            
            for i, j in zip(self.p.Fire_types.keys(), self.p.Fire_types.values()):
                
                self.Managed_fire[j] = []
                
                for a in self.agents:
                    
                    if i in a.Fire_vals.keys():
                        
                        self.Managed_fire[j].append(np.array(a.Fire_vals[i]).reshape(self.p.ylen, self.p.xlen) * self.AFT_scores[type(a).__name__])

                self.Managed_fire[j] = np.nansum([x for x in self.Managed_fire[j]], 
                                                 axis = 0)
                                                                    

        #################################
        ### Add deforestation fire
        #################################
        
        #self.Managed_fire['deforestation'] = deforestation(self)

        
        #################################
        ### apply constraints
        #################################
        
        self.fire_constraints()


        ### Total up managed fire

        self.Managed_fire['Total']  = np.nansum([x for x in self.Managed_fire.values() if type(x) != np.float64], 
                                                 axis = 0)
        

################################################################
### Constraints on fire not captured by DAFI / AFT calculations
################################################################
        
        
    def fire_constraints(self):
        
        '''top down constraints on fire'''
        
        for c in self.Observers.values():
            
            if 'ct' in type(c[0]).__name__:
                
                c.constrain()
        
    
    #######################################################################
    
    ### Background fire
    
    #######################################################################
    
    
    def calc_background_ignitions(self):
        
        ''' Accidental ignitions'''
        
        ### Get background rate
        self.Background_ignitions = np.array(self.Observers['background_rate'].Fire_vals[0]).reshape(self.ylen, self.xlen)


    def calc_arson(self):

        ''' Arson '''        

        ### Get arson
        self.Arson                = np.array(self.Observers['arson'].Fire_vals[0]).reshape(self.ylen, self.xlen)
        
        
    def calc_escaped_fires(self):
        
        pass
    
    
    #####################################################################################
    
    ### scheduler
    
    #####################################################################################
    
    def step(self):
        
        ### ls distribution
        self.ls.get_vals()
        self.allocate_X_axis()

        ### afr distribution
        self.agents.compete()
        self.allocate_Y_axis()

        ### AFT distribution
        self.agents.sub_compete()
        self.allocate_AFT()

        ### Fire use
        self.agents.fire_use()
        self.calc_BA(group_by = 'Land_cover')
        
        #################################################
        ### Background & arson ignitions
        #################################################
        
        if 'background_rate' in self.Observers.keys():
        
            self.Observers['background_rate'].ignite()
            self.calc_background_ignitions()
                
        if 'arson' in self.Observers.keys():
        
            self.Observers['arson'].ignite()
            self.calc_arson()
               
        
        ### Suppression
        self.agents.fire_suppression()
        self.calc_escaped_fires()
         
        ### update
        self.update()
    
    
    def update(self):
        
        self.p.timestep += 1
        self.record()       ### store data in model object
        self.write_out()    ### write data to disk
        
    
    ####################################################################
    
    ### Reporters
    
    ####################################################################
    
    def record(self):
        
        ''' choose data to stash in ram '''
        
        self.results['Managed_fire'].append(deepcopy(self.Managed_fire))        
        self.results['Background_ignitions'].append(deepcopy(self.Background_ignitions))
        self.results['Arson'].append(deepcopy(self.Arson))
    
    
    def write_out(self):
        
        '''choose data to write'''
                
        
        pass
    
    
    ####################################################################
    
    ### End conditions
    
    ####################################################################
    
    def end(self):
        
        pass
    

    

