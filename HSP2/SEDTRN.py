''' Copyright (c) 2020 by RESPEC, INC.
Author: Robert Heaphy, Ph.D.
License: LGPL2
'''

from numpy import array, zeros, where
from math import log10, exp
from HSP2.ADCALC import advect
from HSP2.utilities  import make_numba_dict

ERRMSG = []

def sedtrn(store, siminfo, uci, ts):
	''' Simulate behavior of inorganic sediment'''

	errorsV = zeros(len(ERRMSG), dtype=int)

	simlen = siminfo['steps']
	delt   = siminfo['delt']
	delt60 = siminfo['delt'] / 60
	delts  = siminfo['delt'] * 60

	advectData = uci['advectData']
	(nexits, vol, VOL, SROVOL, EROVOL, SOVOL, EOVOL) = advectData

	ui = make_numba_dict(uci)
	svol = ui['VOL']
	nexits = int(ui['NEXITS'])

	# table SANDFG
	sandfg = ui['SANDFG']   # 1: Toffaleti method, 2:Colby method, 3:old HSPF power function

	# table SED-GENPARM
	bedwid = ui['BEDWID']
	bedwrn = ui['BEDWRN']
	por    = ui['POR']
	
	# table SED-HYDPARM
	len_   = ui['LEN']
	delth  = ui['DELTH']
	db50   = ui['DB50']

	UUNITS = 1  # assume english units for now
	# evaluate some quantities used in colby and/or toffaleti sand transport simulation methods
	if UUNITS == 1:
		db50e = db50
		db50m = db50 * 304.8
	else: 
		db50e = db50 * 3.28
		db50m = db50 * 1000.0	
	slope = delth / len_
	
	# SAND PARAMETERS; table SAND-PM
	sand_d      = ui['D']
	sand_w      = ui['W'] * delts   # convert settling velocity from m/sec to m/ivl
	sand_rho    = ui['RHO']
	sand_ksand  = ui['KSAND']
	sand_expsnd = ui['EXPSND']

	# SILT PARAMETERS; table SILT-CLAY-PM --- note: first occurance is silt
	ui_silt = uci['SILT']
	silt_d     = ui_silt['D']
	silt_w     = ui_silt['W'] * delts        # convert settling velocity from m/sec to m/ivl
	silt_rho   = ui_silt['RHO']
	silt_taucd = ui_silt['TAUCD']
	silt_taucs = ui_silt['TAUCS']
	silt_m     = ui_silt['M'] * delt60 / 24.0  # convert erodibility coeff from /day to /ivl
	
	# CLAY PARAMETERS; table SILT-CLAY-PM --- note: second occurance is clay
	ui_clay = uci['CLAY']
	clay_d     = ui_clay['D']
	clay_w     = ui_clay['W'] * delts   # convert settling velocity from m/sec to m/ivl
	clay_rho   = ui_clay['RHO']
	clay_taucd = ui_clay['TAUCD']
	clay_taucs = ui_clay['TAUCS']
	clay_m     = ui_clay['M']	* delt60 / 24.0  # convert erodibility coeff from /day to /ivl
	
	# bed sediment conditions; table BED-INIT
	beddep      = ui['BEDDEP']
	sand_bedfr  = ui['SANDFR']
	silt_bedfr  = ui['SILTFR']
	clay_bedfr  = ui['CLAYFR']	
	total_bedfr = sand_bedfr + silt_bedfr + clay_bedfr
	if abs(total_bedfr - 1.0) > 0.01:
		pass # error message: sum of bed sediment fractions is not close enough to 1.0

	# suspended sediment concentrations; table ssed-init
	sand_ssed1  = ui['SSED1']
	silt_ssed2  = ui['SSED2']
	clay_ssed3  = ui['SSED3']
	total_ssed4 = sand_ssed1 + silt_ssed2 + clay_ssed3

	# get input time series- inflow of sediment is in units of mg.ft3/l.ivl (english) or mg.m3/l.ivl (metric)
	TAU   = ts['TAU']
	AVDEP = ts['AVDEP']
	AVVEL = ts['AVVEL']
	ISED1 = ts['ISED1']   # if present, else ISED is identically zero;  sand
	ISED2 = ts['ISED2']   # if present, else ISED is identically zero;  silt
	ISED3 = ts['ISED3']   # if present, else ISED is identically zero;  clay
	ISED4 = ISED1 + ISED2 + ISED3
	
	if sandfg != 3:
		RO   = ts['RO']
		HRAD = ts['HRAD']
		TWID = ts['TWID']

	htfg = int(ui['HTFG'])
	if htfg == 0 and sandfg != 3:
		TW = ts['TW']
		TW = where(TW < -100.0, 20.0, TW)
	
	# preallocate storage for computed time series
	# WASH     = ts['WASH']    = zeros(simlen)    # washload concentration, state variable
	# SAND     = ts['SAND']    = zeros(simlen)    # sandload oncentration, state variable
	# BDSAND   = ts['BDSAND']  = zeros(simlen)    # bed storage of sand, state variable
	# SDCF1_11 = ts['WASH']    = zeros(simlen)    # deposition of washload on bed
	# SDCF1_21 = ts['WASH']    = zeros(simlen)    # total outflow of washload from RCHRES
	# SDCF1_12 = ts['WASH']    = zeros(simlen)    # exchange of sand between bed and suspended storage
	# SDCF1_22 = ts['WASH']    = zeros(simlen)    # total outflow of sandload from rchres
	# SDCF2_1  = ts['SDCF2_1'] = zeros((simlen, nexits))  # washload outflow by gate
	# SDCF2_2  = ts['SDCF2_2'] = zeros((simlen, nexits))  # sandload outflow by gate
	# ossand = zeros(nexits)
	SSED1 = ts['SSED1'] = zeros(simlen)  # suspended sand concentration
	SSED2 = ts['SSED2'] = zeros(simlen)  # suspended silt concentration
	SSED3 = ts['SSED3'] = zeros(simlen)  # suspended clay concentration
	SSED4 = ts['SSED4'] = zeros(simlen)  # suspended sediment concentration
	RSED1 = ts['RSED1'] = zeros(simlen)  # sediment storages - suspended sand
	RSED2 = ts['RSED2'] = zeros(simlen)  # sediment storages - suspended silt
	RSED3 = ts['RSED3'] = zeros(simlen)  # sediment storages - suspended clay
	RSED4 = ts['RSED4'] = zeros(simlen)  # sediment storages - bed sand
	RSED5 = ts['RSED5'] = zeros(simlen)  # sediment storages - bed silt
	RSED6 = ts['RSED6'] = zeros(simlen)  # sediment storages - bed clay
	RSED7 = ts['RSED7'] = zeros(simlen)  # sediment storages - total sand
	RSED8 = ts['RSED8'] = zeros(simlen)  # sediment storages - total silt
	RSED9 = ts['RSED9'] = zeros(simlen)  # sediment storages - total clcay
	RSED10 = ts['RSED10'] = zeros(simlen)  # sediment storages - total sand silt clay
	TSED1 = ts['TSED1'] = zeros(simlen)  # Total sediment storages by fraction
	TSED2 = ts['TSED2'] = zeros(simlen)  # Total sediment storages by fraction
	TSED3 = ts['TSED3'] = zeros(simlen)  # Total sediment storages by fraction
	BEDDEP= ts['BEDDEP']= zeros(simlen)  # Bed depth
	DEPSCR1 = ts['DEPSCR1'] = zeros(simlen)  # Deposition (positive) or scour (negative) - sand
	DEPSCR2 = ts['DEPSCR2'] = zeros(simlen)  # Deposition (positive) or scour (negative) - silt
	DEPSCR3 = ts['DEPSCR3'] = zeros(simlen)  # Deposition (positive) or scour (negative) - clay
	DEPSCR4 = ts['DEPSCR4'] = zeros(simlen)  # Deposition (positive) or scour (negative) - total
	ROSED1 = ts['ROSED1'] = zeros(simlen)  # Total outflows of sediment from the rchres - sand
	ROSED2 = ts['ROSED2'] = zeros(simlen)  # Total outflows of sediment from the rchres - silt
	ROSED3 = ts['ROSED3'] = zeros(simlen)  # Total outflows of sediment from the rchres - clay
	ROSED4 = ts['ROSED4'] = zeros(simlen)  # Total outflows of sediment from the rchres - total
	OSED1 = zeros((simlen, nexits))
	OSED2 = zeros((simlen, nexits))
	OSED3 = zeros((simlen, nexits))
	OSED4 = zeros((simlen, nexits))

	fact = 1.0 / total_bedfr  # normalize fractions to sum to one
	sand_bedfr *= fact
	silt_bedfr *= fact
	clay_bedfr *= fact
	rhomn = sand_bedfr * sand_rho + silt_bedfr * silt_rho + clay_bedfr * clay_rho

	volsed = len_ * bedwid * beddep * (1.0 - por)  # total volume of sediment particles- ft3 or m3
	rwtsed = volsed * rhomn  # total weight relative to water- rhomn is in parts/part (same as  kg/l)
	rwtsed = rwtsed * 1.0E06  # converts from kg/l to mg/l

	# find the weight of each fraction- units are (mg/l)*ft3 or (mg/l)*m3
	sand_wt_rsed4 = sand_ssed1 * rwtsed
	silt_wt_rsed5 = silt_ssed2 * rwtsed
	clay_wt_rsed6 = clay_ssed3 * rwtsed

	# find the total quantity (bed and suspended) of each sediment size fraction
	sand_rsed1 = sand_ssed1 * vol
	sand_rssed1 = sand_t_rsed7 = sand_rsed1 + sand_wt_rsed4

	silt_rsed2 = silt_ssed2 * vol
	silt_rssed2 = silt_t_rsed8 = silt_rsed2 + silt_wt_rsed5

	clay_rsed3 = clay_ssed3 * vol
	clay_rssed3 = clay_t_rsed9 = clay_rsed3 + clay_wt_rsed6

	tsed1 = sand_rsed1 + silt_rsed2 + clay_rsed3
	tsed2 = sand_wt_rsed4 + silt_wt_rsed5 + clay_wt_rsed6
	tsed3 = total_rsed10 = sand_t_rsed7 + silt_t_rsed8 + clay_t_rsed9

	wsande = sand_w * 3.28 / delts  # convert fall velocity from m/ivl to ft/sec

	#################### END PSED

	for loop in range(simlen):

		ised1 = ISED1[loop]
		ised2 =	ISED2[loop]
		ised3 = ISED3[loop]

		# perform any necessary unit conversions
		if UUNITS == 2:  # uci is in metric units
			avvele = AVVEL[loop] * 3.28
			avdepm = AVDEP[loop]
			avdepe = AVDEP[loop] * 3.28
			rom    = RO[loop]
			hrade  = HRAD[loop]  * 3.28
			twide  = TWID[loop]  * 3.28
		else:         # uci is in english units
			avvele = AVVEL[loop]
			avdepm = AVDEP[loop] * 0.3048
			avdepe = AVDEP[loop]
			rom    = RO[loop] * 0.0283
			hrade  = HRAD[loop]
			twide  = TWID[loop]
		tau = TAU[loop]
		tw  = TW[loop]

		# Following is routine #&COHESV() to simulate behavior of cohesive sediments (silt and clay)
		# compute bed fractions based on relative storages
		totbed  = silt_wt_rsed5 + clay_wt_rsed6
		frcsed1 = silt_wt_rsed5 / totbed  	if totbed > 0.0 else 0.5
		frcsed2 = clay_wt_rsed6 / totbed  	if totbed > 0.0 else 0.5

		vol = VOL[loop]
		srovol = SROVOL[loop]
		erovol = EROVOL[loop]
		sovol = SOVOL[loop, :]
		eovol = EOVOL[loop, :]
		silt_ssed2, rosed2, osed2 = advect(ised2, silt_ssed2, nexits, svol * 43560, vol * 43560, srovol, erovol, sovol, eovol)
		silt_rsed2 = silt_ssed2 * vol  	# calculate exchange between bed and suspended sediment
		# vols = svol
	
		# consider deposition and scour
		depscr2 = bdexch(avdepm, silt_w, tau, silt_taucd, silt_taucs, silt_m, vol, frcsed1, silt_rsed2, silt_wt_rsed5) if avdepe > 0.17 else 0.0
		silt_ssed2 = silt_rsed2 / vol  if vol > 0.0 else -1.0e30

		clay_ssed3, rosed3, osed3 = advect(ised3, clay_ssed3, nexits, svol * 43560, vol * 43560, srovol, erovol, sovol, eovol)
		clay_rsed3 = clay_ssed3 * vol  	# calculate exchange between bed and suspended sediment

		# consider deposition and scour
		depscr3 = bdexch(avdepm, clay_w, tau, clay_taucd, clay_taucs, clay_m, vol, frcsed2, clay_rsed3, clay_wt_rsed6) if avdepe > 0.17 else 0.0
		clay_ssed3 = clay_rsed3 / vol  if vol > 0.0 else -1.0e30
		# end COHESV()
	
		# compute fine sediment load
		fsl    = silt_ssed2 + clay_ssed3
		ksand  = sand_ksand
		expsnd = sand_expsnd

		# simulate sandload.  done after washload because washload affects sand transport if the colby method is used
		# Following code is #$SANDLD()
		sands = sand_ssed1  # save starting concentration value
		if vol > 0.0:          # rchres contains water
			if rom > 0.0 and avdepe > 0.17:   # there is outflow from the rchres- perform advection
				# calculate potential value of sand
				if sandfg == 1:            	# case 1 toffaleti equation
					gsi = toffaleti(avvele, db50e, hrade, slope, tw, wsande)
					psand = (gsi * twide * 10.5) / rom   # convert potential sand transport rate to a concentration in mg/l
				elif sandfg == 2:    # case 2 colby equation
					gsi, ferror, d50err, hrerr, velerr = colby(avvele, db50m, hrade, fsl, tw)
					if ferror == 1:
						pass # ERRMSG: fatal error ocurred in colby method- one or more  variables went outside valid range- warn and switch to toffaleti method
						gsi = toffaleti(avvele, db50e, hrade, slope, tw, wsande) # switch to toffaleti method
					psand = (gsi * twide * 10.5) / rom  # convert potential sand transport rate to conc in mg/l
				elif sandfg == 3:      # case 3 input power function
					psand = ksand * avvele**expsnd

				prosnd = (sands * srovol) + (psand * erovol)  # calculate potential outflow of sand during ivl
				pscour = (vol * psand) - (svol * sands) + prosnd - ised1  # qty.vol/l.ivl  # calculate potential bed scour from, or to deposition
				if pscour < sand_wt_rsed4:              # potential scour is satisfied by bed storage;
					# new conc. of sandload is potential conc.
					scour          = pscour
					sand_ssed1     = psand
					sand_rsed1     = sand_ssed1 * vol
					sand_wt_rsed4 -= scour
				else:            # potential scour cannot be satisfied;  all of the available bed storage is scoured
					scour         = sand_wt_rsed4
					sand_wt_rsed4 = 0.0
					sand_ssed1    = (ised1 + scour + sands * (svol - srovol)) / (vol + erovol)  # calculate new conc. of suspended sandload
					sand_rsed1    = sand_ssed1 * vol   # calculate new storage of suspended sandload
				rosed1 = srovol * sands + erovol * sand_ssed1  # calculate total amount of sand leaving rchres during ivl
				osed1  = sovol * sands + eovol * sand_ssed1  # calculate amount of sand leaving through each exit gate in qty.vol/l.ivl
			else:             # no outflow (still water) or water depth less than two inches
				sand_ssed1  = 0.0
				sand_rsed1  = 0.0
				scour       = -ised1 - (sands * svol)
				sand_wt_rsed4 -= scour
				rosed1 = 0.0
				osed1 = zeros(nexits)
		else:               # rchres is dry; set sand equal to an undefined number
			sand_ssed1    = -1.0e30
			sand_rsed1    = 0.0
			scour         = -ised1 - (sands * svol)  # calculate total amount of sand settling out during interval; this is equal to sand inflow + sand initially present
			sand_wt_rsed4 -= scour  # update bed storage
			rosed1 = 0.0
			osed1 = zeros(nexits)
		depscr1 = -scour   # calculate depth of bed scour or deposition; positive for deposition
		# end SANDLD()

		# set small concentrations to zero
		if abs(sand_ssed1) < 1.0e-15:   # small conc., set to zero
			if depscr1 > 0.0:           # deposition has occurred, add small storage to deposition
				depscr1 += sand_rsed1
				sand_wt_rsed4 += sand_rsed1
			else:      # add small storage to outflow
				rosed1 += sand_rsed1
				depscr1 = 0.0
				if nexits > 1:
					for n in range(1,nexits+1):
						if osed1[n] > 0.0:
							osed1[n] += sand_rsed1
							break
			sand_rsed1 = 0.0
			sand_ssed1 = 0.0

		if abs(silt_ssed2) < 1.0e-15:   # small conc., set to zero
			if depscr2 > 0.0:           # deposition has occurred, add small storage to deposition
				depscr2 += silt_rsed2
				silt_wt_rsed5 += silt_rsed2
			else:      # add small storage to outflow
				rosed2 += silt_rsed2
				depscr2 = 0.0
				if nexits > 1:
					for n in range(1, nexits+1):
						if osed2[n] > 0.0:
							osed2[n] += silt_rsed2
							break
			silt_rsed2 = 0.0
			silt_ssed2 = 0.0

		if abs(clay_ssed3) < 1.0e-15:   # small conc., set to zero
			if depscr3 > 0.0:           # deposition has occurred, add small storage to deposition
				depscr3 += clay_rsed3
				clay_wt_rsed6 += clay_rsed3
			else:      # add small storage to outflow
				rosed3 += clay_rsed3
				depscr3 = 0.0
				if nexits > 1:
					for n in range(1, nexits+1):
						if osed3[n] > 0.0:
							osed3[n] += clay_rsed3
							break
			clay_rsed3 = 0.0
			clay_ssed3 = 0.0

		osed4 = zeros(nexits)
		# calculate total quantity of material in suspension and in the bed; check bed conditions
		osed4 += osed1
		sand_rssed1 = sand_t_rsed7 = sand_rsed1 + sand_wt_rsed4  # total storage in mg.vol/l
		if sand_wt_rsed4 == 0.0:       # warn that bed is empty
			pass # errmsg

		osed4 += osed2
		silt_rssed2 = silt_t_rsed8 = silt_rsed2 + silt_wt_rsed5    # total storage in mg.vol/l
		if silt_wt_rsed5 == 0.0:         # warn that bed is empty
			pass # errmsg

		osed4 += osed3
		clay_rssed3 = clay_t_rsed9 = clay_rsed3 + clay_wt_rsed6  	# total storage in mg.vol/l
		if clay_wt_rsed6 == 0.0:   # warn that bed is empty
			pass # errmsg

		# find the volume occupied by each fraction of bed sediment- ft3 or m3
		volsed = (sand_wt_rsed4 / (sand_rho * 1.0e06)
			   +  silt_wt_rsed5 / (silt_rho * 1.0e06)
			   +  clay_wt_rsed6 / (clay_rho * 1.0e06))

		total_ssed4  = sand_ssed1 + silt_ssed2 + clay_ssed3
		tsed1  = sand_rsed1 + silt_rsed2 + clay_rsed3
		tsed2  = sand_wt_rsed4 +  silt_wt_rsed5 +  clay_wt_rsed6
		tsed3  = total_rsed10 = sand_t_rsed7 + silt_t_rsed8 + clay_t_rsed9
		depscr4 = depscr1 + depscr2 + depscr3
		rosed4  = rosed1 + rosed2 + rosed3
	
		# find total depth of sediment
		volsed = volsed / (1.0 - por)        #  allow for porosit
		beddep = volsed / (len_ * bedwid)     # calculate thickness of bed- ft or m
		if beddep > bedwrn:
			pass  # Errormsg:  warn that bed depth appears excessive

		svol = vol  # svol is volume at start of time step, update for next time thru

		SSED1[loop] = sand_ssed1
		SSED2[loop] = silt_ssed2
		SSED3[loop] = clay_ssed3
		SSED4[loop] = total_ssed4
		RSED1[loop] = sand_rsed1
		RSED2[loop] = silt_rsed2
		RSED3[loop] = clay_rsed3
		RSED4[loop] = sand_wt_rsed4
		RSED5[loop] = silt_wt_rsed5
		RSED6[loop] = clay_wt_rsed6
		RSED7[loop] = sand_t_rsed7
		RSED8[loop] = silt_t_rsed8
		RSED9[loop] = clay_t_rsed9
		RSED10[loop]= total_rsed10
		TSED1[loop] = tsed1
		TSED2[loop] = tsed2
		TSED3[loop] = tsed3
		BEDDEP[loop]= beddep
		DEPSCR1[loop] = depscr1
		DEPSCR2[loop] = depscr2
		DEPSCR3[loop] = depscr3
		DEPSCR4[loop] = depscr4
		ROSED1[loop] = rosed1
		ROSED2[loop] = rosed2
		ROSED3[loop] = rosed3
		ROSED4[loop] = rosed4
		OSED1[loop] = osed1
		OSED2[loop] = osed2
		OSED3[loop] = osed3
		OSED4[loop] = osed4

	if nexits > 1:
		for i in range(nexits):
			ts['OSED1' + str(i+1)] = OSED1[:, i]
			ts['OSED2' + str(i + 1)] = OSED2[:, i]
			ts['OSED3' + str(i + 1)] = OSED3[:, i]
			ts['OSED4' + str(i + 1)] = OSED4[:, i]

	return errorsV, ERRMSG


def bdexch (avdepm, w, tau, taucd, taucs, m, vol, frcsed, susp, bed):
	''' simulate deposition and scour of a cohesive sediment fraction- silt or clay'''
	if w > 0.0 and tau < taucd and susp > 1.0e-30:    # deposition will occur
		expnt  = -w  / avdepm * (1.0 - tau / taucd)
		depmas = susp * (1.0 - exp(expnt))
		susp  -= depmas
		bed   += depmas
	else:
		depmas = 0.0            # no deposition- concentrations unchanged

	if tau > taucs and m > 0.0:   # scour can occur- units are:  m- kg/m2.ivl  avdepm- m  scr- mg/l
		scr = frcsed * m / avdepm * 1000.0 * (tau/taucs - 1.0)
		scrmas = min(bed, scr * vol) # check availability of material ???

		# update storages
		susp += scrmas
		bed  -= scrmas
	else:                      # no scour
		scrmas = 0.0
	return depmas - scrmas  # net deposition or scour


''' Sediment Transport in Alluvial Channels, 1963-65 by Bruce Colby.
This report explains the following empirical algorithm.'''

def colby(v, db50, fhrad, fsl, tempr):
# 	Colby's method to calculate the capacity of the flow to transport sand.
#
#   The colby method has the following units and applicable ranges of variables.
#         average velocity.............v.......fps.........1-10 fps
#         hydraulic radius.............fhrad...ft..........1-100 ft
#        median bed material size.....db50....mm..........0.1-0.8 mm
#         temperature..................tmpr....deg f.......32-100 deg.
#         fine sediment concentration..fsl.....mg/liter....0-200000 ppm
#         total sediment load..........gsi.....ton/day.ft..
	G = zeros((5,9,7))      # defined by Figure 26
	G[1, 1, 1], G[2, 1, 1], G[3, 1, 1], G[4, 1, 1] = 1.0,   0.30,   0.06,    0.00
	G[1, 2, 1], G[2, 2, 1], G[3, 2, 1], G[4, 2, 1] = 3.00,  3.30,   2.50,    2.00
	G[1, 3, 1], G[2, 3, 1], G[3, 3, 1], G[4, 3, 1] = 5.40,  9.0,    10.0,    20.0
	G[1, 4, 1], G[2, 4, 1], G[3, 4, 1], G[4, 4, 1] = 11.0,  26.0,   50.0,   150.0
	G[1, 5, 1], G[2, 5, 1], G[3, 5, 1], G[4, 5, 1] = 17.0,  49.0,   130.0,  500.0
	G[1, 6, 1], G[2, 6, 1], G[3, 6, 1], G[4, 6, 1] = 29.0,  101.0,  400.0,  1350.0
	G[1, 7, 1], G[2, 7, 1], G[3, 7, 1], G[4, 7, 1] = 44.0,  160.0,  700.0,  2500.0
	G[1, 8, 1], G[2, 8, 1], G[3, 8, 1], G[4, 8, 1] = 60.0,  220.0,  1000.0, 4400.0
	G[1, 1, 2], G[2, 1, 2], G[3, 1, 2], G[4, 1, 2] = 0.38,  0.06,   0.0,    0.0
	G[1, 2, 2], G[2, 2, 2], G[3, 2, 2], G[4, 2, 2] = 1.60,  1.20,   0.65,   0.10
	G[1, 3, 2], G[2, 3, 2], G[3, 3, 2], G[4, 3, 2] = 3.70,  5.0,    4.0,    3.0
	G[1, 4, 2], G[2, 4, 2], G[3, 4, 2], G[4, 4, 2] = 10.0,  18.0,   30.0,   52.0
	G[1, 5, 2], G[2, 5, 2], G[3, 5, 2], G[4, 5, 2] = 17.0,  40.0,   80.0,   160.0
	G[1, 6, 2], G[2, 6, 2], G[3, 6, 2], G[4, 6, 2] = 36.0,  95.0,   230.0,  650.0
	G[1, 7, 2], G[2, 7, 2], G[3, 7, 2], G[4, 7, 2] = 60.0,  150.0,  415.0,  1200.0
	G[1, 8, 2], G[2, 8, 2], G[3, 8, 2], G[4, 8, 2] = 81.0,  215.0,  620.0,  1500.0
	G[1, 1, 3], G[2, 1, 3], G[3, 1, 3], G[4, 1, 3] = 0.14,  0.0,    0.0,    0.0
	G[1, 2, 3], G[2, 2, 3], G[3, 2, 3], G[4, 2, 3] = 1.0,   0.60,   0.15,   0.0
	G[1, 3, 3], G[2, 3, 3], G[3, 3, 3], G[4, 3, 3] = 3.30,  3.00,   1.70,   0.50
	G[1, 4, 3], G[2, 4, 3], G[3, 4, 3], G[4, 4, 3] = 11.0,  15.0,   17.0,   14.0
	G[1, 5, 3], G[2, 5, 3], G[3, 5, 3], G[4, 5, 3] = 20.0,  35.0,   49.0,   70.0
	G[1, 6, 3], G[2, 6, 3], G[3, 6, 3], G[4, 6, 3] = 44.0,  85.0,   150.0,  250.0
	G[1, 7, 3], G[2, 7, 3], G[3, 7, 3], G[4, 7, 3] = 71.0,  145.0,  290.0,  500.0
	G[1, 8, 3], G[2, 8, 3], G[3, 8, 3], G[4, 8, 3] = 100.0, 202.0,  400.0,  700.0
	G[1, 1, 4], G[2, 1, 4], G[3, 1, 4], G[4, 1, 4] = 0.0,   0.0,    0.0,    0.0
	G[1, 2, 4], G[2, 2, 4], G[3, 2, 4], G[4, 2, 4] = 0.70,  0.30,   0.06,   0.0
	G[1, 3, 4], G[2, 3, 4], G[3, 3, 4], G[4, 3, 4] = 2.9,   2.3,    1.0,    0.06
	G[1, 4, 4], G[2, 4, 4], G[3, 4, 4], G[4, 4, 4] = 11.5,  13.0,   12.0,   7.0
	G[1, 5, 4], G[2, 5, 4], G[3, 5, 4], G[4, 5, 4] = 22.0,  31.0,   40.0,   50.0
	G[1, 6, 4], G[2, 6, 4], G[3, 6, 4], G[4, 6, 4] = 47.0,  84.0,   135.0,  210.0
	G[1, 7, 4], G[2, 7, 4], G[3, 7, 4], G[4, 7, 4] = 75.0,  140.0,  240.0,  410.0
	G[1, 8, 4], G[2, 8, 4], G[3, 8, 4], G[4, 8, 4] = 106.0, 190.0,  350.0,  630.0
	G[1, 1, 5], G[2, 1, 5], G[3, 1, 5], G[4, 1, 5] = 0.0,   0.0,    0.0,    0.0
	G[1, 2, 5], G[2, 2, 5], G[3, 2, 5], G[4, 2, 5] = 0.44,  0.06,   0.0,    0.0
	G[1, 3, 5], G[2, 3, 5], G[3, 3, 5], G[4, 3, 5] = 2.8,   1.8,    0.6,    0.0
	G[1, 4, 5], G[2, 4, 5], G[3, 4, 5], G[4, 4, 5] = 12.0,  12.5,   10.0,   4.5
	G[1, 5, 5], G[2, 5, 5], G[3, 5, 5], G[4, 5, 5] = 24.0,  30.0,   35.0,   37.0
	G[1, 6, 5], G[2, 6, 5], G[3, 6, 5], G[4, 6, 5] = 52.0,  78.0,   120.0,  190.0
	G[1, 7, 5], G[2, 7, 5], G[3, 7, 5], G[4, 7, 5] = 83.0,  180.0,  215.0,  380.0
	G[1, 8, 5], G[2, 8, 5], G[3, 8, 5], G[4, 8, 5] = 120.0, 190.0,  305.0,  550.0
	G[1, 1, 6], G[2, 1, 6], G[3, 1, 6], G[4, 1, 6] = 0.0,   0.0,    0.0,    0.0
	G[1, 2, 6], G[2, 2, 6], G[3, 2, 6], G[4, 2, 6] = 0.3,   0.0,    0.0,    0.0
	G[1, 3, 6], G[2, 3, 6], G[3, 3, 6], G[4, 3, 6] = 2.9,   1.4,    0.3,    0.0
	G[1, 4, 6], G[2, 4, 6], G[3, 4, 6], G[4, 4, 6] = 14.0,  11.0,   7.7,    3.0
	G[1, 5, 6], G[2, 5, 6], G[3, 5, 6], G[4, 5, 6] = 27.0,  29.0,   30.0,   30.0
	G[1, 6, 6], G[2, 6, 6], G[3, 6, 6], G[4, 6, 6] = 57.0,  75.0,   110.0,  170.0
	G[1, 7, 6], G[2, 7, 6], G[3, 7, 6], G[4, 7, 6] = 90.0,  140.0,  200.0,  330.0
	G[1, 8, 6], G[2, 8, 6], G[3, 8, 6], G[4, 8, 6] = 135.0, 190.0,  290.0,  520.0
	  
	F = zeros((6,11))    # defined by Figure 24
	F[1, 1],  F[2, 1],  F[3, 1],  F[4, 1],  F[5, 1]  = 1.0,  1.1,  1.6,   2.6,   4.2
	F[1, 2],  F[2, 2],  F[3, 2],  F[4, 2],  F[5, 2]  = 1.0,  1.1,  1.65,  2.75,  4.9
	F[1, 3],  F[2, 3],  F[3, 3],  F[4, 3],  F[5, 3]  = 1.0,  1.1,  1.7,   3.0,   5.5
	F[1, 4],  F[2, 4],  F[3, 4],  F[4, 4],  F[5, 4]  = 1.0,  1.12, 1.9,   3.6,   7.0
	F[1, 5],  F[2, 5],  F[3, 5],  F[4, 5],  F[5, 5]  = 1.0,  1.17, 2.05,  4.3,   8.7
	F[1, 6],  F[2, 6],  F[3, 6],  F[4, 6],  F[5, 6]  = 1.0,  1.2,  2.3,   5.5,   11.2
	F[1, 7],  F[2, 7],  F[3, 7],  F[4, 7],  F[5, 7]  = 1.0,  1.22, 2.75,  8.0,   22.0
	F[1, 8],  F[2, 8],  F[3, 8],  F[4, 8],  F[5, 8]  = 1.0,  1.25, 3.0,   9.6,   29.0
	F[1, 9],  F[2, 9],  F[3, 9],  F[4, 9],  F[5, 9]  = 1.0,  1.3,  3.5,   12.0,  43.0
	F[1, 10], F[2, 10], F[3, 10], F[4, 10], F[5, 10] = 1.0,  1.4,  4.9,   22.0,  120.0
	  
	T = array([[1.2,  1.15, 1.10, 0.96, 0.90, 0.85, 0.82], 
			   [1.35, 1.25, 1.12, 0.92, 0.86, 0.80, 0.75],
			   [1.60, 1.40, 1.20, 0.89, 0.80, 0.72, 0.66], 
			   [2.00, 1.65, 1.30, 0.85, 0.72, 0.63, 0.55]]).T                     # Temperature adjustment, Figure 24

	DF   = array([0.10, 0.20, 0.30, 0.60, 1.00, 2.00, 6.00, 10.00, 20.00, 1.E2])               # Depths for Figure 24	
	CF   = array([0.00, 1.E4, 5.E4, 1.E5, 1.5E5])  	                       # Concentrations of sediment for Figure 24
	P    = array([0.60, 0.90, 1.0, 1.0, 0.83, 0.60, 0.40, 0.25, 0.15, 0.09, 0.05])  # Percentage Effect for Figure 24
	DP   = array([0.10, 0.15, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00]) # Median diameters for Figure 24
	DG   = array([0.10, 1.00, 10.0, 100.0])                              # Depth values for Figure 26
	VG   = array([1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0, 10.0])           # Velocity values for Figure 26
	D50G = array([0.10, 0.20, 0.30, 0.40, 0.60, 0.80])                  # Median values for figure 26
	TEMP = array([32.0, 40.0, 50.0, 70.0, 80.0, 90.0, 100.0])  # Temperatures for lookup in Figure 26
	  
	ferror = 0
	d50err = 0
	hrerr  = 0
	velerr = 0

	id501 = 0
	id502 = 0
	id1   = 0
	iv1   = 0
	it1   = 0
	if not 0.80 >= db50 >=  0.10:  # D50G limits
		ferror = 1
		d50err = 1
		return
	for id501, db50x in enumerate(D50G):
		if db50x > db50:
			break
	id502 = id501 + 1
	zz1 = log10(D50G[id501])
	zz2 = log10(D50G[id502])
	zzratio = (log10(db50) - zz1) / (zz2 - zz1)

	if not 100.0 >= fhrad >= 0.10:  # DG limits
		ferror = 1
		hrerr  = 1
		return
	for id1,dgx in enumerate(DG):
		if dgx > DG:
			break
	id2 = id1 + 1		
	xx1 = log10(DG[id1])
	xx2 = log10(DG[id2])
	xxratio = (log10(fhrad) - xx1) / ((xx2 - xx1))
		
	if not 10.0 >= v >= 1.0:  # VG limits
		ferror = 1
		velerr = 1
		return
	for iv1, vx in enumerate(VG):
		if vx > v:
			break
	iv2 = iv1 + 1
	yy1 = log10(VG[iv1])
	yy2 = log10(VG[iv2])
	yyratio = (log10(v) - yy1) / (yy2 - yy1)		
		
	tmpr = min(100.0, max(32.0, tempr * 1.8 + 32.0))

	x = zeros((3,3))
	xa= zeros(3)
	xg= zeros(3)
	for i,i1 in [(1, id1), (2, id2)]:                # DO 200 I= 1,2;   I1    = II(I)
		for j, j1 in [(1, iv1), (2, iv2)]:           # DO 190 J= 1,2;  J1    = JJ(J)
			for k, k1 in [(1, id501), (2, id502)]:   # DO 180 K= 1,2; K1    = KK(K)
				if G[i1,j1,k1] > 0.0:
					x[j,k] = log10(G[i1,j1,k1])					
				else:	
					for j3 in range(j1,8):           # DO 140 J3= J1,7
						if G[i1,j3,k1] > 0.0:
							break
					x[j,k] = log10(G[i1,j3,k1]) + (log10(VG[j1] / VG[j3])) * (log10(G[i1,j3+1,k1] / G[i1,j3,k1])) / (log10(VG[j3+1] / VG[j3]))
				
		xa[1] = x[1,1] + (x[1,2] - x[1,1]) * zzratio
		xa[2] = x[2,1] + (x[2,2] - x[2,1]) * zzratio
		xn3   = xa[2] - xa[1]
		xg[i] = xa[1] + xn3 * yyratio

	xn4  = xg[2] - xg[1]
	gtuc = 10.0**(xg[1] + (xn4 * xxratio))   # uncorrected gt in lb/sec/ft

	# Adjustment coefficient for temperature
	if abs(tmpr - 60.0) <= 1.0e-5:
		cft = 1.0
	else:
		for it1, tempx in enumerate(TEMP):
			if tempx > tmpr:
				break
		it2 = it1 + 1

		xt11 = log10(T[it1,id1])
		xt21 = log10(T[it2,id1])
		xt12 = log10(T[it1,id2])
		xt22 = log10(T[it2,id2])
		
		xnt   = log10(tmpr / TEMP[it1]) / log10(TEMP[it2] / TEMP[it1])
		xct1  = xt11 + xnt * (xt21 - xt11)
		xct2  = xt12 + xnt * (xt22 - xt12)
		cft = 10.0**(xct1 + (xct2 - xct1) * xxratio)

	# fine sediment load correction; (i.e. cohesive sediment or wash) load  in mg/liter
	if fsl <= 10.0:
		cff = 1.0
	else:
		for id1, dfx in enumerate(DF):
			if dfx > fhrad:
				break
		id2 = id1 + 1

		if1 = 0
		if fsl > 1.0E+4:
			if1 = 4
			if2 = 5
			ERRMSG = '***** SUBROUTINE COLBY -- FSL WENT > 1.E+4'
		else:	
			for if1, cfx in enumerate(CF):
				if cfx > fsl:
					break
			if2 = if1 + 1

		xf11 = log10(F[if1,id1])
		xf22 = log10(F[if2,id2])
		xf12 = log10(F[if1,id2])
		xf21 = log10(F[if2,id1])
			
		xnt = (fsl - CF[if1]) / (CF[if2] - CF[if1])
		xct1  = xf11 + xnt * (xf21 - xf11)
		xct2  = xf12 + xnt * (xf22 - xf12)
		xnt = log10(fhrad / DF[id1]) / log10(DF[id2] / DF[id1])
		cff = 10.0**(xct1 + xnt * (xct2 - xct1))
	tcf = cft * cff - 1.0

	# Percent effect correction for median diameter'''
	if 0.30 >= db50 >= 0.20:
		cfd = 1.0
	else:
		for ip1, db50x in enumerate(DP):
			if db50x > db50:
				break
		ip2 = ip1 + 1
	
		p1  = log10(P[ip1])
		p2  = log10(P[ip2])
		xnt = log10(db50 / DP[ip1]) / log10(DP[ip2] / DP[ip1])
		
		cfd = 10.0**(p1 + xnt * (p2 -p1))

	return gtuc * (cfd * tcf + 1.0), ferror, d50err, hrerr, velerr


def toffaleti(v, fdiam, fhrad, slope, tempr, vset, gsi):
	''' Toffaleti's method to calculate the capacity of the flow to transport sand.'''

	tmpr = tempr * 1.80 + 32.0   # degrees c to degrees f

	# For water temperatures greater than 32f and less than 100f the kinematic viscosity is
	vis = 4.106e-4 * tmpr**-0.864

	# Assuming the d50 grain size is approximately equal to the Geometric mean grain size 
	# and sigma-g = 1.5, the d65 grain size can be determined as 1.17*d50.
	d65 = 1.17 * fdiam
	cnv = 0.1198 + 0.00048 * tmpr
	cz  = 260.67 - 0.667 * tmpr
	tt  = 1.10 * (0.051 + 0.00009 * tmpr)
	zi  = vset * v / (cz * fhrad * slope)
	if zi < cnv:
		zi = 1.5 * cnv

	# The manning-strickler equation is used here to Determine the hydraulic radius
	# component due to Grain roughness (r').  Taken from the 1975 asce  
	# "sedimentation engineering",pg. 128.
	rprime = ((v**1.5) * (d65**0.25) / (slope**0.75)) * 0.00349
	ustar  = (rprime * slope * 32.2)**0.5
	
	afunc  = (vis * 1.0e5)**0.333 / (10.0 * ustar)
	if   afunc <= 0.500:  ac = (afunc / 4.89)**-1.45 
	elif afunc <= 0.660:  ac = (afunc / 0.0036)**0.67
	elif afunc <= 0.720:  ac = (afunc / 0.29)**4.17
	elif afunc <= 1.25:   ac = 48.0
	elif afunc >  1.25:   ac = (afunc / 0.304)**2.74

	k4func = afunc * slope * d65 * 1.0e5
	if   k4func <= 0.24:   k4 = 1.0
	elif k4func <= 0.35:   k4 = (k4func**1.10) * 4.81
	elif k4func >  0.35:   k4 = (k4func** (-1.05)) * 0.49

	ack4 = ac * k4
	if ack4 - 16.0 < 0.0:
		ack4 = 16.0
		k4   = 16.0 / ac
	oczu = 1.0 + cnv - 1.5  * zi
	oczm = 1.0 + cnv - zi
	oczl= 1.0 + cnv - 0.756 * zi
	zinv = cnv - 0.758 * zi
	zm  = -zinv
	zn  = 1.0 + zinv
	zo  = -0.736 * zi
	zp  = 0.244  * zi
	zq  = 0.5    * zi

	# Cli has been multiplied by 1.0e30 to keep it from Exceeding the computer overflow limit
	cli = (5.6e+22 * oczl * (v**2.333) / fhrad**(zm) / ((tt * ac * k4 * fdiam)**1.667)
	    / (1.0 + cnv) / ((fhrad / 11.24)**(zn) - (2.0 * fdiam)**oczl))
	p1  = (2.0 * fdiam / fhrad)**(zo / 2.0)
	c2d = cli * p1 * p1 / 1.0e+30

	# Check to see if the calculated value is reasonable (< 100.0), and adjust it if it is not.
	if c2d > 100.0:
		cli = cli * 100.0 / c2d
	cmi = 43.2 * cli * (1.0 + cnv) * v * (fhrad**zm)  	# Cmi has been multiplied by 1.0e30 to keep it from computer overflow

	# upper layer transport capacity
	fd11 = fhrad / 11.24
	fd25 = fhrad / 2.5
	gsu  = (cmi * (fd11**zp) * (fd25**zq) * (fhrad**oczu - (fd25**oczu)))/(oczu * 1.0e+30)

	gsm = (cmi * (fd11**zp) * (fd25**(oczm) - (fd11**oczm))) / (oczm * 1.0e+30) # middle layer transport capacity
	gsl = (cmi * ((fd11**(zn)) - ((2.0 * fdiam)**(oczl)))) / (oczl * 1.0e+30)  	# lower layer transport capacity
	gsb = (cmi * ((2.0 * fdiam)**(zn))) / 1.0e+30  	                            # bed layer transport capacity

	return max(0.0, gsu + gsm + gsl + gsb)              # Total transport capacity of the rchres (tons/day/ft)
