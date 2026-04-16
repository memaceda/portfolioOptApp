import axios from "axios";
import React, { useContext, useState } from "react";

const url = process.env.NEXT_PUBLIC_API_URL || "http://localhost:4000";
console.log("Current API URL:", process.env.NEXT_PUBLIC_API_URL);

const api = {
    test: async () => {
        const data = await axios.post(
            `${url}/test`,
            {
                method: "POST",
                headers: {
                    'Content-type': 'application-json',
                    'Access-Control-Allow-Origin': '*',
                },
            }
        );
        return data;
    },
    resourceUpload: async (apiData) => {
        console.log(apiData)
        const data = await axios.post(
            `${url}/resourceUpload`,
            apiData,
            {
                headers: {
                    'Access-Control-Allow-Origin': '*',
                },
            }
        );
        return data;
    },
    generateWindBinaries: async (apiData) => {
        const data = await axios.post(
            `${url}/generateWindBinaries`,
            apiData,
            {
                method: "POST",
                headers: {
                    'Content-type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                },
            }
        );
        return data;
    },
    windInputGeneration: async (apiData) => {
        const data = await axios.post(
            `${url}/windInputGeneration`,
            apiData,
            {
                method: "POST",
                headers: {
                    'Content-type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                },
            }
        );
        return data;
    },
    kiteInputGeneration: async (apiData) => {
        const data = await axios.post(
            `${url}/kiteInputGeneration`,
            apiData,
            {
                method: "POST",
                headers: {
                    'Content-type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                },
            }
        );
        return data;
    },
    waveInputGeneration: async (apiData) => {
        const data = await axios.post(
            `${url}/waveInputGeneration`,
            apiData,
            {
                method: "POST",
                headers: {
                    'Content-type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                },
            }
        );
        return data;
    },
    portfolioOptimization: async (apiData) => {
        const data = await axios.post(
            `${url}/portfolioOptimization`,
            apiData,
            {
                method: "POST",
                headers: {
                    'Content-type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                },
            }
        );
        return data;
    },
    portfolioPlots: async (portfolio) => {
        const data = await axios.post(
            `${url}/portfolioPlots`,
            portfolio,
            {
                method: "POST",
                headers: {
                    'Content-type': 'application/json',
                    'Access-Control-Allow-Origin': '*',
                },
                responseType: 'blob'
            }
        );
        return data;
    },
};

export default api;