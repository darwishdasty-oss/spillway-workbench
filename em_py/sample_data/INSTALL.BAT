@echo off 
cls
cd\ 
prompt $p $g
echo.
echo.
echo.
echo I will now create two directories on drive C: 
echo The executable files will be placed in C:\CAV 
echo The data files will be placed in C:\CAV\DATA 
echo If you do not want this to happen press Control-C 
echo.
pause 
mkdir C:\CAV 
mkdir C:\CAV\DATA
CD\CAV
A:XFER
