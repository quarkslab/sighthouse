docker-compose -f create-certs.yml up
sysctl vm.max_map_count=2097152
docker-compose up
