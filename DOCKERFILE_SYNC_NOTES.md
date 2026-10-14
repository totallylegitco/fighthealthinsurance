# Dockerfile Synchronization Notes

## Important: Keep Dockerfiles in Sync with CI Configuration

This project has multiple Dockerfiles that may need to be updated when CI configuration changes:

### File Locations:
- **CI Configuration**: `.github/workflows/ci.yml`
- **Main Dockerfile**: `k8s/Dockerfile`  
- **Ray Combined Dockerfile**: `k8s/ray/CombinedDockerfile`

### When to Review and Update:

#### If changes are made to `.github/workflows/ci.yml`, review these Dockerfiles:

1. **`k8s/Dockerfile`** - Used for main application deployments
2. **`k8s/ray/CombinedDockerfile`** - Used for staging/ray-based deployments

#### Common Changes to Watch For:

1. **System Package Dependencies**
   - If CI installs new `apt` packages for build dependencies
   - Example: database client headers (`libpq-dev`)
   
2. **Python Build Requirements**
   - New build tools or development headers
   - Example: `python3-dev`, `pkg-config`, `build-essential`
   
3. **External Tools**
   - New tools needed for testing or building
   - Example: `pandoc`, `texlive`, `wkhtmltopdf`

4. **Build Steps and Commands**
   - Django management commands like blog metadata generation
   - File copying operations that affect runtime functionality
   - Working directory changes and file permissions

### Action Items When CI Changes:
1. Review the CI changes for new system dependencies
2. Check if those dependencies are needed in production/staging
3. Update both Dockerfiles with the same dependencies
4. Maintain consistent package ordering for build optimization
5. Test both Docker builds to ensure they work
