@echo off
cls 
echo.
echo.
echo.
echo I am now ready to begin copying files from the 
echo the Source and Data Diskette which should be in 
echo Drive A:
echo.
pause
copy A:*.EXE C:\CAV 
copy A:*. C:\CAV\DATA 
copy A:*.SCR C:\CAV 
copy A:*.BAT C:\CAV 
copy A:GETFUN.COM C:\CAV
cls
echo.
echo.
echo.
echo I am now ready to begin copying files from
echo the Executable I diskette.  Please place 
echo Executable I into Drive A: 
xcopy A:*.EXE C:\CAV /W
cls
echo.
echo.
echo.
echo I am now ready to begin copying files from
echo the Executable II diskette.  Please place
echo Executable II into Drive A: 
xcopy A:*.EXE C:\CAV /W
cls
echo.
echo.
echo.
echo All of the executable files are now in C:\CAV 
echo All of the data files are now in C:\CAV\DATA 
echo.
echo.
echo.
echo You can now begin analyzing chutes and spillways for
echo their cavitation potential.  Good Luck!
echo.
pause
