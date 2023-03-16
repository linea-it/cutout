# curl -sSL "https://scienceserver.linea.org.br/data/cutout_des_sample_tiles.tar.gz" -o cutout_des_sample_tiles.tar.gz \
wget "https://scienceserver.linea.org.br/data/cutout_des_sample_tiles.tar.gz" -o cutout_des_sample_tiles.tar.gz \
&& tar -xzf cutout_des_sample_tiles.tar.gz \
&& for z in *.fits.fz; do funpack "$z"; done \
&& rm *.fits.fz \
&& rm cutout_des_sample_tiles.tar.gz \
&& ls -ltr
