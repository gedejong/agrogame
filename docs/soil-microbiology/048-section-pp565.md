### Section pp565

which is
t1/2/H11005ln 2/H11408k/H11015 0.693 /H11408k (7)
The mean residence time (turnover time of an amount of substrate at steady
state equivalent in size to the starting amount) for ﬁrst-order reactions is equal to1/k. Note that t
mrtfor zero-order reactions is S0/H11408k.
ENZYMATIC KINETICS
Because extracellular enzymes are responsible for much of the substrate depletion
in soils, the kinetics of enzyme reactions can be used to model substrate depletion.Enzyme kinetics are represented by the hyperbolic, Michaelis–Menton equation,
(8)
where V
mis the maximum reaction rate (concentration time/H110021), and is proportional
to the total mass of enzyme in the soil (and hence to the total active biomass), andK
mis the Michaelis–Menton, or half-saturation, constant and is the substrate con-
centration at which the reaction occurs at half the maximum velocity, Vm/H114082. Kmis
inversely related to enzyme–substrate afﬁnity, which tends to have higher valuesin soil than in aqueous solutions and to decrease when soil slurries are shaken;therefore K
mis inversely proportional to diffusivity.
Figure 16.2 illustrates how Michaelis–Menton kinetics contain both ﬁrst- and
zero-order regions.dS
dtVS
KS/H11005/H11001m
m436 Chapter 16 The Dynamics of Soil Organic Matter
KmVmax Velocity of reaction (v)Vm
2
Substrate concentration, A
FIGURE 16.2 Graphical expression of the Michaelis–Menton kinetic parameters for an enzy-
matic reaction.Ch16-P546807.qxd  11/18/06  7:13 PM  Page 436
At high substrate concentrations ( S/H11022/H11022Km), the equation simpliﬁes to
(9)
which describes a zero-order reaction, and under very low substrate concentra-
tions ( S/H11021/H11021Km), the equation simpliﬁes to
(10)
which describes a ﬁrst-order reaction. Because of the combined linear and expo-
nential forms of Sin the equation, the Michaelis–Menton cannot be solved for St
analytically; however, solutions are easily calculated iteratively using spreadsheet
software.
MICROBIAL GROWTH
The equations described above have one limitation in common; none can account
for microbial growth. As microorganisms consume a substrate, one portion is usedfor maintenance energy requirements and if enough substrate is available, theremainder will be used to support growth. As microorganisms grow and multiplythey will exert an increasing demand on the remaining substrate, thereby chang-ing the kinetics of decomposition. Three equations can be used to describe micro-bial growth: the exponential, logistic, and Monod equations.
When rapidly consuming substrate, microbes are known to grow exponentially,
(11)
where Nis the number (biomass) of cells and µis the growth rate. Changes in bio-
mass can be equated to changes in substrate by dividing the biomass by the yield(y), which is the mass of cells generated per mass of substrate consumed:
(12)
Substituting Eq. (11) for dN/H11408dtinto Eq. (12), we obtain the following equation in
terms of substrate depletion,
(13)
/H11002/H11005dS
dtN
ytµ/H11002/H11005dS
dtdN
dt y1dN
dtN/H11005µdS
dtVS
Kk'S /H11005/H11005m
mdS
dtV/H11005mReaction Kinetics 437Ch16-P546807.qxd  11/18/06  7:13 PM  Page 437
where Ntis the biomass at any given time. Measuring biomass at all given times is
unrealistic, therefore Ntcan be described in terms of initial biomass, N0, such that
Nt/H11005N0/H11001Nt/H11002N0, and the above equation expands to
and collecting terms
(14)
Expressing all terms as substrate, considering that the total amount of substrate
consumed since t/H110050 is S0/H11002St/H11005(Nt/H11002N0)/H11408y, and letting X0/H11005N0/H11408ywhere X0
becomes the amount of substrate needed to produce N0, then the differential form
of the exponential equation for substrate depletion is
(15)
While the exponential equation links substrate depletion with microbial growth,
it is well recognized that microbes do not grow exponentially at all times. Rather,microbial populations grow to a limit ( K). As the population increases, the growth
rate (µ) decreases due to competition among individuals for increasingly scarce sub-
strate resources. Microbial growth to a limit is expressed by the logistic equation
(16)
A similar exercise of algebra to express the logistic equation in terms of substrate,
considering that Kis the maximum biomass (original biomass plus that generated
by converting all the original substrate into biomass), yields the differential equa-tion for logistic growth in terms of substrate depletion:
(17)
Initially, S/H11005S
0and the reaction rate is governed primarily by X0. As the micro-
bial population grows, Sdecreases such that the ﬁrst term in the equation above
decreases while the second term increases. Therefore, two competing trends gov-ern the substrate depletion rate. The rate of substrate depletion is maximized at/H11002dS/H11408dt
max/H11005µ(S0/H11001X0)/H114084. The differential form of the logistic equation can be
integrated and solved for Stto give
(18)SSXSX
S
Xet
t/H11005/H11001/H11002/H11001
/H11001/H11002/H110020000
0
011⎛
⎝⎜⎜⎜⎜⎞
⎠⎟⎟⎟⎟µ/H11002/H11005/H11001/H11001/H11002dS
dtS
SXSXS µ
000()
0⎛
⎝⎜⎜⎜⎜⎞
⎠⎟⎟⎟⎟dN
dtN
KN /H11005/H11002µ1⎛
⎝⎜⎜⎜⎞
⎠⎟⎟⎟/H11002/H11005 /H11001/H11002dS
dtSXSµ()00/H11002/H11005 /H11001/H11002 dS
dtN
yNN
ytµ00 ()µ/H11002/H11005 /H11001 /H11002dS
dtN
yN
yN
ytµµµ00438 Chapter 16 The Dynamics of Soil Organic MatterCh16-P546807.qxd  11/18/06  7:13 PM  Page 438
Monod kinetics are the most general kinetic expressions because they relate
substrate depletion both to changes in population density and to changes in sub-strate concentration. The basic relationship is
(19)
which appears similar to the Michaelis–Menton equation but has some subtle dif-
ferences: µ/H11032 is the speciﬁc growth rate ( µ/H11032/H11005µ/N
t), µmaxis the maximum growth
rate when substrate is not limiting, and Ksis the Monod constant, which is similar
to the Michaelis–Menton constant. The differential equation describing Monodkinetics with growth in terms of substrate depletion is
(20)
As with the Michaelis–Menton equation, the integrated form of Monod kinetics
cannot be solved for S
t, but can be solved for t, and then the substrate concentra-
tion can be determined iteratively.
While apparently complex, Monod kinetics can be simpliﬁed under certain
conditions to yield each of the kinetic equations described above. Table 16.1 sum-marizes the various kinetic equations and the conditions under which they will occur.For instance, when the initial concentration of microbial biomass is much greaterthan the initial substrate concentration (e.g., X
0/H11022/H11022S0), then the term ( S0/H11001X0/H11002S)
in the Monod equation can be approximated to X0and the Monod equation is sim-
pliﬁed to the Michaelis–Menton equation used to describe enzyme kinetics.
MODELING THE DYNAMICS 
OF DECOMPOSITION AND 
NUTRIENT TRANSFORMATIONS
Models can be used to gain an understanding of the processes and controls
involved in nutrient cycles, to generate data on the size of various pools and therates at which nutrients are transformed, and to make predictions when experi-ments are inappropriate. While conceptual models may be sufﬁcient for the ﬁrsttask, only quantitative models can achieve the latter tasks. Quantitative models ofSOM and nutrient dynamics are attempts to describe soil biological processesrather than strictly mathematical expressions and statistical procedures used toﬁnd best-ﬁtting curves. Fitting model equations to carbon and nutrient mineral-ization curves provides estimates of the amount of mineralized product released(e.g., CO
2) and the rate at which the product (e.g., NO 3/H11002) is made available to
plants. Models range from single-equation kinetic representations such as thoseoutlined above to large mechanistic models that account for many components ofan ecosystem and require computers for generating the results./H11002/H11005/H11001/H11001/H11002dS
dtS
KSSXS
sµmax 0 0 ()µµ'S
KSs/H11005/H11001maxModeling the Dynamics of Decomposition 439Ch16-P546807.qxd  11/18/06  7:13 PM  Page 439
TABLE 16.1 The Monod Kinetic Equation, Its Simpliﬁcations, and the Conditions under Which the Simpliﬁcations Can Be Made
Solve
Condition Outcome Kinetics Differential form Integrated form for S?
Monod N
S0/H11022/H11022Ks Ks/H11001S/H11015S Exponential St/H11005S0/H11001X0/H11002X0ektY
S0/H11021/H11021Ks Ks/H11001S/H11015Ks Logistic Y
X0/H11022/H11022S0 S0/H11001X0/H11002S/H11015X0Michaelis– N
Menton
X0/H11022/H11022S0 S0/H11001X0/H11002S/H11015X0First order St/H11005S0e/H11002ktY
and S0/H11021/H11021KsKs/H11001S/H11015Ks
X0/H11022/H11022S0 S0/H11001X0/H11002S/H11015X0Zero order St/H11005S0/H11002kt Y
and S0/H11022/H11022KsKs/H11001S/H11015S/H11002/H11005dS
dtSX
KkS
sµmax 0/H11032SS KS
SVtts
t00
m/H11002/H11001 /H11005 ln⎛
⎝⎜⎜⎜⎜⎜⎞
⎠⎟⎟⎟⎟⎟⎟
/H11002/H11005/H11001/H11005/H11001dS
dtSX
KSkS
KSssµmax0/H11032SSXSXSXe
tt/H11005/H11001 /H11002/H11001
/H11001/H11002/H110020000
0
011⎛
⎝⎜⎜⎜⎜⎜⎞
⎠⎟⎟⎟⎟⎟
µ/H11002/H11005 /H11001 /H11002dSdtS
KSXS
sµmax()00/H11002/H11005 /H11001 /H11002dSdtSXS µmax()00KSSSXKXX
ststln ( )ln
000
0⎛
⎝⎜⎜⎜⎜⎜⎞
⎠⎟⎟⎟⎟⎟⎛
⎝⎜⎜ /H11005/H11001/H11001⎜⎜⎜⎜⎞
⎠⎟⎟⎟⎟⎟/H11002/H11001()
max
SX t00µ /H11002/H11005/H11001/H11001/H11002
dSdtS
KSSXS
sµmax()00
/H11002/H11005 /H11005dS
dtXkµmax 0/H11032440Ch16-P546807.qxd  11/18/06  7:13 PM  Page 440
SIMPLE MODELS
The kinetics of plant nutrient transformations has been of interest for a long time,
particularly the kinetics of N mineralization. Stanford and Smith (1972) began bydescribing net N mineralization using a simple ﬁrst-order model, N/H11005N
0(1/H11002e/H11002kt),
where Nis the amount of nitrogen mineralized at time tand N0is the amount of
potentially mineralizable nitrogen. Several modiﬁcations to ﬁrst-order models, aswell as other kinetic models, have been proposed to account for experimentalobservations of large initial ﬂushes of mineralization or for lags before the initia-tion of mineralization (Ellert and Bettany, 1988). In selecting a model for N andS net mineralization, one should generally increase model complexity incremen-tally to obtain a suitable ﬁt, keep the number of parameters to a minimum, andknow that no single model will ﬁt data for all soils under all conditions, whilesome conditions will be adequately described by several models.
Because they play different roles in plants and the environment that lead to dif-
fering dynamics, there are few short-term or single-season models for C like thereare for N and other plant nutrients. Soil organic matter models generally project thelong-term sustainability of changes in soil C, but there are a number of ways todescribe the short-term decomposition of organic residues during the ﬁrst fewmonths after introduction to the soil. Field and laboratory experiments have shownthat initial decomposition rates of litter are generally independent of the amountof biomass added unless it exceeds 1.5% of the dry soil weight. Decomposition ofplant residues has been experimentally found to be reasonably well described byﬁrst-order rate kinetics. The use of ﬁrst-order kinetics to describe the decomposi-tion of SOM implies that the microbial inoculum potential of soil is not limitingthe decomposition rate (e.g., X
0/H11022/H11022S0, from the previous section). This is true, in
large part, because soil microbial biomass often has a fast growth rate relative tothe length of most decomposition studies.
Jenny (1941) published a simple model that used a combination of zero-order
and ﬁrst-order components to describe changes in soil organic matter,
where Xis the organic C or N content of the soil and Ais the addition rate (mass t
/H110021)
used to describe accumulations or losses not associated with decomposition.However, this model does not account for the heterogeneous nature of SOM, i.e.,kis constant. Several approaches have been used to accommodate for the chang-
ing nature of organic matter during decomposition, such as making ka function of
time or including additional compartments.
Experimental data for the decomposition of added plant residues or manures can
be closely ﬁt using the summation of two ﬁrst-order equations in the general form
where Cis the soil C content at any given time, Aand Bare the proportions of the two
pools, and k
Aand kBare the ﬁrst-order constants for each of the pools. In the caseCA e B ekt ktAB /H11005/H11001/H11002/H11002dX
dtAk X/H11005/H11002Modeling the Dynamics of Decomposition 441Ch16-P546807.qxd  11/18/06  7:13 PM  Page 441
illustrated in Fig. 16.3, the ﬁrst pool of the manured treatment represented 5% of the
soil C and had a turnover time of 40 days in the laboratory. The second pool repre-sented 45% of the C with a laboratory turnover time of 3 years. The curve represent-ing the fertilized plots showed that the ﬁrst pool represented 2% of the C with aturnover time similar to that of the manured (40 days). The second pool represent-ing 48% of the C had a turnover time of 5 years. The remainder of the C was knownfrom 
14C dating to have a turnover time of 500 to 1000 years and therefore did not
contribute CO 2to the decomposition of the inputs. The example demonstrates how
the partitioning of organic matter between labile and more resistant fractions altersthe decomposition dynamics. Lack of participation of a signiﬁcant proportion of thesoil C in respiration suggests the need for an additional pool or compartment, andthis knowledge led to the development of the multicompartmental models.
Differences in the ability of simple models to model short-term versus long-
term decomposition dynamics were highlighted by Sleutel et al. (2005), who
compared the performance of ﬁrst-order, sum of ﬁrst-order, combination of zero-order and ﬁrst-order, second-order, and Monod kinetic models for extrapolationfrom short-term data. They concluded that the sum of ﬁrst-order and Monod mod-els performed best in estimating stable organic C, but did not ﬁt short-term min-eralization well, while the ﬁrst-order and combination of zero-order and ﬁrst-ordermodels should not be used for extrapolating from short-term data.
Only a portion of the actual decomposition is accounted for when determining
the decomposition rate ( k) by measuring CO
2output or the amount of C left in the soil.442 Chapter 16 The Dynamics of Soil Organic Matter
005001500
100020002500
50 100 150 200
Time (days)Manured
FertilizedC mineralization ( mg g/H110021 soil)C min (manure) /H11005 1130 (1 /H11002e/H110020.025T) /H11005 9570 (1 /H11002 e/H110020.00066T)
C min (fertilized) /H11005 390 (1 /H11002 e/H110020.026T) /H11005 9510 (1 /H11002 e/H110020.00042T)
FIGURE 16.3 The ﬁt of the sum of two ﬁrst-order curves describing C mineralization in soil
from a manured and fertilized long-term plot during a 220-day incubation.Ch16-P546807.qxd  11/18/06  7:13 PM  Page 442
Microorganisms use C compounds for biosynthesis, forming new cellular or extra-
cellular material, and as an energy supply. In the latter process, CO 2, microbial cells,
and waste products are produced. Under aerobic conditions, the amount of wasteproducts produced is not usually high, and the amount of biosynthesis, or produc-tion of microbial cells, can be calculated from CO
2data. This requires knowledge
of yield or efﬁciency of substrate conversion to microbial biomass,
C/H11005Ci[1/H11001Y/H11408(100 /H11002Y)]
where Cis the substrate decomposed, Cithe CO 2–C evolved, and Ythe efﬁciency
(yield, or sometimes CUE for C utilization efﬁciency) of the use of Cfor biosyn-
thesis, expressed as a percentage of the total Cutilized for production of microbial
material. The decomposition rate constants ( k), corrected for biosynthesis, differ
signiﬁcantly from the uncorrected ones (Table 16.2). Growth efﬁciencies of 40–60%are generally considered realistic for the decomposition of soluble constituents; othercompounds, such as waxes and cellulose, result in lower efﬁciencies. Aromaticssuch as lignin appear to be largely cometabolized by fungi. This involves enzy-matic degradation of the substrate but little uptake of the breakdown products. Thefungi gain little, if any, energy for growth and incorporate little C during thedecomposition of the aromatics. Therefore, aromatic decomposition occurs onlyin the presence of available substrate. Where data are available only over extendedperiods, it is not possible to calculate true decomposition values and microbialgrowth efﬁciency because CO
2is evolved from both the original substrate and the
turnover of microbial cells.
MULTICOMPARTMENTAL MODELS
The distinction between simple kinetic models and multicompartmental models 
is somewhat arbitrary since the sum of exponentials model above described CModeling the Dynamics of Decomposition 443
TABLE 16.2 First-Order Decay Constants with and without Correction for Microbial
Biosynthesis during the Decomposition of Organic Compounds Added to Soil under Laboratory
Conditions
k(day/H110021)
Time of
incubation Corrected for Corrected for
Material (days) Uncorrected CUE /H1100520% CUE /H1100560%
Straw–rye 14 0.02 0.03 0.11
Hemicellulose 14 0.03 0.04 0.11Lignin 365 0.003 0.006 —Native grass 30 0.006 0.008 0.02Fungal cytoplasm 10 0.04 0.05 0.17
Fungal cell wall 10 0.02 0.03 0.07Ch16-P546807.qxd  11/18/06  7:13 PM  Page 443
mineralization from two pools or compartments. Generally, compartmental mod-
els are needed when a single equation is insufﬁcient to describe the multiple trans-formation processes that occur simultaneously in soils. A multicompartmentalmodel is depicted graphically as a set of boxes, each of which represents a pool orcompartment. Most often, the pools are deﬁned conceptually, but they can also bemeasurable fractions of SOM (see Alternative SOM Models). A series of arrows con-necting the various pools represents transformations of organic matter or a nutri-ent element from one form to the other. The graphical representation of the modelcan be written as a series of simultaneous reactions. Some simple compartmentalmodels can be solved analytically (e.g., in equation form), such as the sum of expo-nentials describe above, but as the models become more complex and include morecompartments, it becomes necessary to solve them numerically.
The advent of computers permitted the solution of complex systems models
that require iterative solving of multiple equations to address multicompartmentdynamics. The modeling of soil biological processes began with ecologists work-ing in natural ecosystems in the 1960s and 1970s. Early modeling in agriculturalsystems focused on crop production in response to physical parameters, rather thanbiological processes. A new emphasis in the 1970s on the environmental impactsof agriculture led to early models of N dynamics, including nitrate leaching anddenitriﬁcation. Further emphasis on agroecology and SOM management in the1980s and 1990s has led to the development of a large number of models of soilorganic matter dynamics. Several reviews comparing many of these models areavailable (e.g., McGill, 1996; Molina and Smith, 1998; Paustian, 1994; Smith et al. ,
1997). A subset of these comparisons is provided in Table 16.3.
Paustian (1994) classiﬁed multicompartmental models of SOM dynamics as
either “process-oriented” or “organism-oriented.” There are far fewer organism-oriented models (Table 16.3), which are sometimes called “food web models” anddescribe the ﬂow of organic matter and nutrients through different functional ortaxonomic groups of soil organisms. Process-oriented models are those that focuson the processes mediating the transformations of organic matter and nutrients, ratherthan on the activity of speciﬁc organisms or groups of organisms. In process-oriented model types, soil organisms, if present, tend to be represented as a generic
biomass or as part of a pool of active SOM. This approach precludes the possibil-ity of modeling changes in organic matter dynamics or nutrient cycling that mightoccur due to changes in the activity or composition of the soil organism commu-nity. Schimel (2001), however, points out that the microbiological underpinningsin process-oriented models are not absent, but are implicit and buried in the equa-tion structure of the model as kinetic constants and response functions.
If most biochemical reactions in soils are mediated by enzymes and follow
Michaelis–Menton kinetics, and if soil microbial populations grow and die backregularly, why is it that most process-oriented models use ﬁrst-order kinetics todescribe SOM and nutrient dynamics (Table 16.3)? As demonstrated previously,Monod or Michaelis–Menton kinetics can be simpliﬁed to ﬁrst-order kineticswhen substrate concentrations are sufﬁciently low. Several studies have shownthat soil respiration usually occurs at 20 to 65% of its maximum potential rate.444 Chapter 16 The Dynamics of Soil Organic MatterCh16-P546807.qxd  11/18/06  7:13 PM  Page 444
TABLE 16.3 Comparison of Basic Attributes of Several Multicompartmental Models of Soil Organic Matter and Nutrient Dynamicsa
Resolution Explicit Nonliving SOM pools Regulation Other
Litter/SOM decomposer by soil Rate nutrient 
Model SpatialbTemporalcdistinction pool No. Names texture kinetics elements
CANDY P, F, C D, Y Separate No 4 Fresh organic matter, Yes First order N
(Franko et al., active SOM, stabilized
1995, 1997) SOM, inert SOM
CENTURY P, F, R, M Separate No 5 Metabolic litter, structural Yes First order N, P, S
(Parton et al., 1987; N, G litter, active SOM, slow 
Parton, 1996; SOM, passive SOM
Kelly et al., 1997)
DAISY P, F, C H Separate No 7 Added OM 1, 2 Yes Michaelis– N
(Hansen et al., 1991; (slow, fast); root OM Menton and 
Mueller et al., 1996) 1, 2; SOM 1, 2; inert ﬁrst order
SOM
DNDC P H, D Separate No 5 Very labile litter, labile Yes First order N
(Li et al., litter, recalcitrant litter,
1992a,b, 1997) humads—labile, 
humads—resistant
ECOSYS S, P, F Mi, H Separate Yes 7 Soluble SOM, adsorbed Yes Monod N, P
(Grant et al., 1993a,b; SOM, microbial SOM,
Grant 2001) microbial residues, 
active SOM, passive SOM, particulate SOM
(Continued )445Ch16-P546807.qxd  11/18/06  7:13 PM  Page 445
TABLE 16.3 —Continued
Resolution Explicit Nonliving SOM pools Regulation Other
Litter/SOM decomposer by soil Rate nutrient 
Model SpatialbTemporalcdistinction pool No. Names texture kinetics elements
Soil food web model P, F Mi, H Separate Yes 4 Labile litter, resistant litter, No Michaelis– N
(Hunt et al., 1984, stable SOM, refractile Menton, 
1987) SOM logistic, and 
ﬁrst order
ITE P, F Mi Separate Yes 2 Biomass, SOM No Michaelis– N
(Thornley and Verberne, Menton and
1989;  Thornley and ﬁrst order
Cannell, 1992)
NCSOIL S D Separate No 5 Litter Pool I—labile, No First order N
(Molina et al., 1983, Pool I—resistant, 
1997) Pool II—labile, 
Pool II—resistant
PHOENIX P, F D, W, Mo Separate Yes 4 Metabolic litter, structural No Monod and N
(McGill et al., 1981) litter, humads, resistant pseudo-ﬁrst 
SOM order
Q-SOIL P, F Y Combined No 1 Single pool No Pseudo-ﬁrst —
(Bosatta and Ågren order
1985, 1994)
RothC P, F, C, R, Mo Separate No 4 Decomposable litter, Yes First order —
(Jenkinson et al., 1987; N, G resistant litter, humus,
Jenkinson, 1990) inert SOM446Ch16-P546807.qxd  11/18/06  7:13 PM  Page 446
SOMM P, F, G D Combined No 3 L—litter, F—humus/ No First order N
(Chertov, 1990; organic debris, Chertov et al., 1997) H—clay-bonded 
humus
VVV P, F D Separate No 6 Non ligniferous litter, Yes First order N
(Van Veen and Paul, 1981; ligniferous litter, Van Veen et al., 1984) protected active SOM, 
nonprotected active SOM, protected recalcitrant SOM, nonprotected recalcitrant SOM
VVV P, F D Separate No 6 Labile litter, structural Yes First order N
(Verberne et al., 1990) litter, recalcitrant litter, 
protected active SOM, nonprotected active 
SOM, old SOM
aWith permission from Paustian (1994), McGill (1996), and Molina and Smith (1998).
bS, microsite; P, plot; F, ﬁeld; C, catchment; R, regional; N, national; G, global.
cMi, minutes; H, hours; D, days; W, weeks; Mo, months; Y , years.447Ch16-P546807.qxd  11/18/06  7:13 PM  Page 447
