#include <stdio.h>
#include <stdbool.h>

#include "log.h"
#include "gp_spec.h"

bool
gp_create_signal_file(const char *pgdata)
{
	FILE *fp;
	char filePath[1024];

	snprintf(filePath, sizeof(filePath), "%s/gp_auto_failover.signal", pgdata);
	log_info("signal file = '%s'", filePath);

	fp = fopen(filePath, "w+");
	if (!fp)
	{
		log_info("Failed to create signal file for auto failover: %m");
		return false;
	}
	fclose(fp);

	return true;
}

