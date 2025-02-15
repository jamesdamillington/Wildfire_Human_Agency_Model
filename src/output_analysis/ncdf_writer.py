# -*- coding: utf-8 -*-
"""
Created on Fri Aug 27 15:54:20 2021

@author: Oli
"""

import netCDF4 as nc
import numpy as np



fn = r'C:\Users\Oli\Documents\PhD\wham\Model Calibration\Total_new_unoc_pars.nc'
ds = nc.Dataset(fn, 'w', format='NETCDF4')


time = ds.createDimension('time', 25)
lat = ds.createDimension('lat', 144)
lon = ds.createDimension('lon', 192)


times = ds.createVariable('time', 'f4', ('time',))
lats = ds.createVariable('lat', 'f4', ('lat',))
lons = ds.createVariable('lon', 'f4', ('lon',))
value = ds.createVariable('value', 'f4', ('time', 'lat', 'lon',))
value.units = 'ba_fraction'


lats[:] = np.arange(-90, 90, 1.25)
lons[:] = np.arange(-180, 180, 1.875)

value[:, :, :] = np.stack([x['Total'] for x  in test.results['Managed_fire']], 
                          axis= 0)

ds.close()

