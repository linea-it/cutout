# curl -sSL "https://scienceserver.linea.org.br/data/cutout_des_sample_tiles.tar.gz" -o cutout_des_sample_tiles.tar.gz \
wget "https://scienceserver.linea.org.br/data/cutout_des_sample_tiles.tar.gz" -O cutout_des_sample_tiles.tar.gz \
&& echo "Extraindo tar.gz" \
&& tar -xzf cutout_des_sample_tiles.tar.gz \
&& echo "Extraindo fits.fz" \
&& for z in *.fits.fz; do funpack "$z"; echo "$z"; done \
&& echo "Removendo arquivos" \
&& rm *.fits.fz \
&& rm cutout_des_sample_tiles.tar.gz \
&& ls -lth \
&& echo "Done!"
