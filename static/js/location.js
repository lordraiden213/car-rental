document.addEventListener("DOMContentLoaded", async function () {
    const provinceSelect = document.getElementById("province");
    const citySelect = document.getElementById("city");
    const barangaySelect = document.getElementById("barangay");

    const formPages = document.querySelectorAll(".form-page");
    const prevButton = document.getElementById("prev-btn");
    const nextButton = document.getElementById("next-btn");
    const submitButton = document.getElementById("submit-btn");

    let currentPage = 0;
    let locationsData = {}; // Stores the fetched location data

    /** Function to display the correct page in the form */
    function showPage(pageIndex) {
        formPages.forEach((page, index) => {
            page.style.display = index === pageIndex ? "block" : "none";
        });

        prevButton.style.display = pageIndex === 0 ? "none" : "inline-block";
        nextButton.style.display = pageIndex === formPages.length - 1 ? "none" : "inline-block";
        submitButton.style.display = pageIndex === formPages.length - 1 ? "inline-block" : "none";
    }

    /** Function to style buttons */
    function styleButtons() {
        [prevButton, nextButton, submitButton].forEach(button => {
            button.style.backgroundColor = "white";
            button.style.color = "black";
            button.style.border = "2px solid black";  
            button.style.padding = "10px 20px";  
            button.style.cursor = "pointer";
        });

        prevButton.style.marginRight = "20px"; // Spacing between Back and Register
    }

    /** Function to add click effect to buttons */
    function addClickEffect(button) {
        button.addEventListener("click", function () {
            this.style.backgroundColor = "red";
            this.style.color = "white";
        });
    }

    /** Function to populate a dropdown */
    function populateDropdown(selectElement, options, placeholder) {
        selectElement.innerHTML = `<option value="" disabled selected>${placeholder}</option>`;
        options.forEach(optionValue => {
            let option = document.createElement("option");
            option.value = optionValue;
            option.textContent = optionValue;
            selectElement.appendChild(option);
        });
        selectElement.style.display = "block";
    }

    /** Fetch location data from the server */
    async function fetchLocations() {
        try {
            const response = await fetch('/get_locations');
            locationsData = await response.json(); // Store the data globally

            let provinces = [];
            Object.values(locationsData).forEach(region => {
                provinces.push(...Object.keys(region.province_list));
            });

            populateDropdown(provinceSelect, provinces.sort(), "Select Province");

        } catch (error) {
            console.error("Error fetching locations:", error);
        }
    }

    /** Handle province selection */
    provinceSelect.addEventListener("change", function () {
        const selectedProvince = this.value;
        citySelect.innerHTML = barangaySelect.innerHTML = ""; // Reset city and barangay
        barangaySelect.style.display = "none";

        let cities = [];

        Object.values(locationsData).forEach(region => {
            if (region.province_list[selectedProvince]) {
                cities = Object.keys(region.province_list[selectedProvince].municipality_list).sort();
            }
        });

        populateDropdown(citySelect, cities, "Select City/Municipality");
    });

    /** Handle city selection */
    citySelect.addEventListener("change", function () {
        const selectedProvince = provinceSelect.value;
        const selectedCity = this.value;
        barangaySelect.innerHTML = "";

        let barangays = [];

        Object.values(locationsData).forEach(region => {
            if (region.province_list[selectedProvince]?.municipality_list[selectedCity]) {
                barangays = region.province_list[selectedProvince].municipality_list[selectedCity].barangay_list.sort();
            }
        });

        populateDropdown(barangaySelect, barangays, "Select Barangay");
    });

    /** Navigation events */
    nextButton.addEventListener("click", function () {
        if (currentPage < formPages.length - 1) {
            currentPage++;
            showPage(currentPage);
        }
    });

    prevButton.addEventListener("click", function () {
        if (currentPage > 0) {
            currentPage--;
            showPage(currentPage);
        }
    });

    // Apply styles and load data
    styleButtons();
    addClickEffect(prevButton);
    addClickEffect(nextButton);
    addClickEffect(submitButton);
    
    fetchLocations(); // Fetch location data on load
    showPage(currentPage); // Show first page initially
});
